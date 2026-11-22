-- One row per transaction reference, from the ledger or from the biller, with one verdict.
-- Each check runs in order and the first that fails decides the status, so the most
-- serious problem (money moved wrongly) wins over the milder ones (paperwork, timing).
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='merchant_ref',
    indexes=[{'columns': ['merchant_ref']}, {'columns': ['business_date']}],
) }}

{#- On incremental runs, redo only the last few days: late settlements can still change them. -#}
{% set recent -%}
    {% if is_incremental() %}>= (select coalesce(max(business_date) - {{ var('lookback_days') }}, '-infinity') from {{ this }}){% else %}is not null{% endif %}
{%- endset %}

with unmatched_settlements as (
    -- (date, amount, fee) of settlement rows we couldn't tie to one payment.
    select distinct txn_date, amount_kobo, fee_kobo
    from {{ ref('int_settlements_matched') }}
    where match_method = 'unmatched'
    and txn_date {{ recent }}
),

ledger as (
    select
        l.*,
        u.txn_date is not null                      as maybe_settled
    from {{ ref('stg_ledger') }} l
    left join unmatched_settlements u
      on u.txn_date = l.business_date
     and u.amount_kobo = l.amount_kobo
     and u.fee_kobo = l.fee_kobo
     where l.business_date {{ recent }}
),

settlements as (
    select
        merchant_ref,
        count(*)                                    as settlement_count,
        bool_or(match_method = 'inferred')          as inferred_match,
        min(amount_kobo)                            as min_amount_kobo,
        max(amount_kobo)                            as max_amount_kobo,
        min(fee_kobo)                               as min_fee_kobo,
        max(fee_kobo)                               as max_fee_kobo,
        sum(settled_amount_kobo)                    as settled_amount_kobo,
        max(settlement_lag_days)                    as settlement_lag_days
    from {{ ref('int_settlements_matched') }}
    where merchant_ref is not null
    and txn_date {{ recent }}
    group by merchant_ref
),

vends as (
    select
        merchant_ref,
        count(*)                                    as vend_count,
        count(*) filter (where vend_status = 'success') as successful_vends,
        min(biller_code)                            as min_biller_code,
        max(biller_code)                            as max_biller_code,
        min(vend_date)                              as vend_date
    from {{ ref('stg_biller_vends') }}
    where merchant_ref is not null
    and vend_date {{ recent }}   -- a vend never happens before its payment
    group by merchant_ref
),

joined as (
    select
        coalesce(l.merchant_ref, v.merchant_ref)    as merchant_ref,
        l.merchant_ref is not null                  as in_ledger,
        coalesce(l.business_date, v.vend_date)      as business_date,
        coalesce(l.biller_code, v.min_biller_code)  as biller_code,
        l.product,
        l.channel,
        l.status                                    as ledger_status,
        l.amount_kobo,
        l.fee_kobo,
        l.maybe_settled,
        s.settlement_count,
        s.inferred_match,
        s.min_amount_kobo, s.max_amount_kobo,
        s.min_fee_kobo, s.max_fee_kobo,
        s.settled_amount_kobo,
        s.settlement_lag_days,
        v.vend_count,
        v.successful_vends,
        v.min_biller_code, v.max_biller_code
    from ledger l
    left join settlements s using (merchant_ref)
    full outer join vends v on v.merchant_ref = l.merchant_ref
    -- A vend just after midnight can belong to a payment from the day before the window.
    -- That's not an orphan: keep only vends whose payment the ledger has never seen.
    where l.merchant_ref is not null
       or not exists (select 1 from {{ ref('stg_ledger') }} x where x.merchant_ref = v.merchant_ref)
)

select
    merchant_ref,
    business_date,
    biller_code,
    product,
    channel,
    ledger_status,
    amount_kobo,
    fee_kobo,
    coalesce(settlement_count, 0)                   as settlement_count,
    settled_amount_kobo,
    settlement_lag_days,
    coalesce(vend_count, 0)                         as vend_count,
    case
        when not in_ledger                                          then 'orphan_vend'
        when ledger_status <> 'successful' and settlement_count > 0 then 'status_mismatch'
        when ledger_status <> 'successful'                          then 'not_applicable'
        -- One of the unreferenced settlements may be this payment's, but we can't tell which.
        when settlement_count is null and maybe_settled             then 'needs_review'
        when settlement_count is null                               then 'missing_settlement'
        when settlement_count > 1                                   then 'duplicate_settlement'
        when min_amount_kobo <> amount_kobo
          or max_amount_kobo <> amount_kobo                         then 'amount_mismatch'
        when min_fee_kobo <> fee_kobo or max_fee_kobo <> fee_kobo   then 'fee_mismatch'
        when inferred_match                                         then 'missing_reference'
        when settlement_lag_days > 1                                then 'late_settlement'
        when vend_count is null                                     then 'missing_vend'
        when vend_count > 1                                         then 'duplicate_vend'
        when successful_vends = 0                                   then 'vend_failed'
        when min_biller_code <> biller_code
          or max_biller_code <> biller_code                         then 'wrong_biller'
        else 'matched'
    end                                             as recon_status
from joined
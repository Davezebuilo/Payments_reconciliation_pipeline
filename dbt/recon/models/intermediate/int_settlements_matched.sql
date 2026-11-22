-- Every settlement row, tied to the ledger transaction it pays for.
-- Most rows carry our reference. For the few that don't, we infer the transaction from
-- (date, amount, fee), but only when the number of unreferenced rows equals the number of
-- unsettled payments sharing those values: then every one of those payments was settled,
-- and since their amounts are identical, which row pairs with which doesn't matter.
-- Anything more ambiguous stays unmatched: a wrong match is worse than none.
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='processor_ref',
    indexes=[{'columns': ['processor_ref']}, {'columns': ['merchant_ref']}, {'columns': ['txn_date']}],
) }}

{#- On incremental runs, redo only the last few days. Matching works day by day, and every
    settlement shares its payment's date, so a window of whole days never splits a match. -#}
{% set recent -%}
    {% if is_incremental() %}>= (select coalesce(max(txn_date) - {{ var('lookback_days') }}, '-infinity') from {{ this }}){% else %}is not null{% endif %}
{%- endset %}

with settlements as (
    select * from {{ ref('stg_processor_settlement') }}
    where txn_date {{ recent }}
),

ledger as (
    select * from {{ ref('stg_ledger') }}
    where business_date {{ recent }}
),

referenced as (
    select distinct merchant_ref from settlements where merchant_ref is not null
),

-- Successful payments that no referenced settlement row pays for.
candidates as (
    select
        l.merchant_ref, l.business_date, l.amount_kobo, l.fee_kobo,
        count(*) over w as n_candidates,
        row_number() over (w order by l.merchant_ref) as pick
    from ledger l
    left join referenced r using (merchant_ref)
    where r.merchant_ref is null
      and l.status = 'successful'
    window w as (partition by l.business_date, l.amount_kobo, l.fee_kobo)
),

unreferenced as (
    select
        processor_ref, txn_date, amount_kobo, fee_kobo,
        count(*) over w as n_rows,
        row_number() over (w order by processor_ref) as pick
    from settlements
    where merchant_ref is null
    window w as (partition by txn_date, amount_kobo, fee_kobo)
),

inferred as (
    select u.processor_ref, c.merchant_ref
    from unreferenced u
    join candidates c
      on c.business_date = u.txn_date
     and c.amount_kobo = u.amount_kobo
     and c.fee_kobo = u.fee_kobo
     and c.pick = u.pick
    where u.n_rows = c.n_candidates
)

select
    s.processor_ref,
    coalesce(s.merchant_ref, i.merchant_ref)               as merchant_ref,
    case
        when s.merchant_ref is not null then 'reference'
        when i.merchant_ref is not null then 'inferred'
        else 'unmatched'
    end                                                     as match_method,
    s.txn_date,
    s.settlement_date,
    s.settlement_lag_days,
    s.amount_kobo,
    s.fee_kobo,
    s.processor_charge_kobo,
    s.settled_amount_kobo
from settlements s
left join inferred i using (processor_ref)
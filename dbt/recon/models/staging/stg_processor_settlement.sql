-- One row per settlement line from the processor. Its file writes money as "1,500.00"
-- and dates as dd/mm/yyyy; both are converted here. Duplicates and missing references
-- are kept on purpose: finding them is the reconciliation's job, not staging's.
{{ config(indexes=[{'columns': ['txn_date']}]) }}

with source as (
    select * from {{ source('raw', 'processor_settlement') }}
    {% if is_incremental() %}
    -- Only files loaded since the last run (a reload gets a new _loaded_at, so it's picked up too).
    -- coalesce: if the table is still empty, max() is NULL and nothing would ever compare greater.
    where _loaded_at > (select coalesce(max(_loaded_at), '-infinity') from {{ this }})
    {% endif %}
)

select
    processor_ref,
    nullif(upper(trim(merchant_reference)), '')             as merchant_ref,
    to_date(txn_date, 'DD/MM/YYYY')                         as txn_date,
    to_date(settlement_date, 'DD/MM/YYYY')                  as settlement_date,
    to_date(settlement_date, 'DD/MM/YYYY')
        - to_date(txn_date, 'DD/MM/YYYY')                   as settlement_lag_days,
    round(replace(amount, ',', '')::numeric * 100)::bigint           as amount_kobo,
    round(replace(fee, ',', '')::numeric * 100)::bigint              as fee_kobo,
    round(replace(processor_charge, ',', '')::numeric * 100)::bigint as processor_charge_kobo,
    round(replace(settled_amount, ',', '')::numeric * 100)::bigint   as settled_amount_kobo,
    lower(trim(status))                                     as status,
    _file_date,
    _loaded_at
from source
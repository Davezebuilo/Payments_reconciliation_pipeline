-- One row per payment attempt, typed and tidied. Money is in kobo (integers) from here on,
-- so sums never pick up floating-point pennies.
{{ config(indexes=[{'columns': ['merchant_ref']}, {'columns': ['business_date']}]) }}

with source as (
    select * from {{ source('raw', 'ledger') }}
    {% if is_incremental() %}
    -- Only files loaded since the last run (a reload gets a new _loaded_at, so it's picked up too).
    -- coalesce: if the table is still empty, max() is NULL and nothing would ever compare greater.
    where _loaded_at > (select coalesce(max(_loaded_at), '-infinity') from {{ this }})
    {% endif %}
)

select
    upper(trim(merchant_ref))                               as merchant_ref,
    customer_id,
    upper(trim(biller_code))                                as biller_code,
    lower(trim(product))                                    as product,
    lower(trim(channel))                                    as channel,
    round(amount::numeric * 100)::bigint                    as amount_kobo,
    round(fee::numeric * 100)::bigint                       as fee_kobo,
    lower(trim(status))                                     as status,
    created_at::timestamptz                                 as created_at,
    -- The business day is Lagos time, whatever time zone the server runs in.
    (created_at::timestamptz at time zone 'Africa/Lagos')::date as business_date,
    _file_date,
    _loaded_at
from source
-- One row per payment attempt, typed and tidied. Money is in kobo (integers) from here on,
-- so sums never pick up floating-point pennies.
with source as (
    select * from {{ source('raw', 'ledger') }}
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
-- One row per vend the biller reports. Amounts already arrive in kobo; times arrive in UTC.
with source as (
    select * from {{ source('raw', 'biller_vends') }}
)

select
    vend_ref,
    nullif(upper(trim(client_reference)), '')               as merchant_ref,
    upper(trim(biller_code))                                as biller_code,
    amount_kobo::bigint                                     as amount_kobo,
    nullif(trim(token), '')                                 as token,
    lower(trim(vend_status))                                as vend_status,
    vended_at::timestamptz                                  as vended_at,
    (vended_at::timestamptz at time zone 'Africa/Lagos')::date as vend_date,
    _file_date,
    _loaded_at
from source
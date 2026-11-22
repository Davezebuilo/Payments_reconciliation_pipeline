-- One row per vend the biller reports. Amounts already arrive in kobo; times arrive in UTC.
{{ config(indexes=[{'columns': ['merchant_ref']}, {'columns': ['vend_date']}]) }}

with source as (
    select * from {{ source('raw', 'biller_vends') }}
    {% if is_incremental() %}
    -- Only files loaded since the last run (a reload gets a new _loaded_at, so it's picked up too).
    -- coalesce: if the table is still empty, max() is NULL and nothing would ever compare greater.
    where _loaded_at > (select coalesce(max(_loaded_at), '-infinity') from {{ this }})
    {% endif %}
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
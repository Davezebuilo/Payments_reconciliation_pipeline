-- Every amount must be above zero and every fee zero or more. Returns the offending rows.
select 'ledger' as source, merchant_ref as ref, amount_kobo, fee_kobo
from {{ ref('stg_ledger') }}
where amount_kobo <= 0 or fee_kobo < 0

union all

select 'processor', processor_ref, amount_kobo, fee_kobo
from {{ ref('stg_processor_settlement') }}
where amount_kobo <= 0 or fee_kobo < 0

union all

select 'biller', vend_ref, amount_kobo, null
from {{ ref('stg_biller_vends') }}
where amount_kobo <= 0
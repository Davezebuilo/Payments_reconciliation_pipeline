-- Nothing in the ledger may fall through the cracks: every transaction needs a verdict.
select l.merchant_ref
from {{ ref('stg_ledger') }} l
left join {{ ref('fct_reconciliation') }} f using (merchant_ref)
where f.merchant_ref is null
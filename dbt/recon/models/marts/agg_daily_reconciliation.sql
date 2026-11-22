-- Daily totals per biller and status: what the dashboard reads.
select
    business_date,
    biller_code,
    recon_status,
    count(*)                    as transactions,
    sum(amount_kobo)            as amount_kobo
from {{ ref('fct_reconciliation') }}
group by business_date, biller_code, recon_status
-- Daily totals per biller and status: what the dashboard reads.
-- issue_group rolls the 14 statuses into the few questions finance actually asks.
select
    business_date,
    biller_code,
    recon_status,
    case
        when recon_status = 'matched' then 'matched'
        when recon_status = 'not_applicable' then 'not_applicable'
        when recon_status = 'needs_review' then 'needs_review'
        when recon_status in ('missing_settlement', 'duplicate_settlement', 'amount_mismatch',
                              'fee_mismatch', 'status_mismatch') then 'money'
        when recon_status in ('missing_vend', 'vend_failed', 'duplicate_vend', 'wrong_biller',
                              'orphan_vend') then 'fulfilment'
        else 'timing'  -- late_settlement, missing_reference: the money arrived, just late or unlabelled
    end                         as issue_group,
    count(*)                    as transactions,
    sum(amount_kobo)            as amount_kobo,
    (sum(amount_kobo) / 100.0)::numeric(18, 2) as amount_naira
from {{ ref('fct_reconciliation') }}
group by 1, 2, 3, 4
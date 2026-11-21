-- The processor can't settle a payment on or before the day it was made.
select processor_ref, txn_date, settlement_date
from {{ ref('stg_processor_settlement') }}
where settlement_lag_days < 1
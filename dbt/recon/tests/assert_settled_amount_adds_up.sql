-- The processor's own arithmetic: settled = amount + fee - its charge.
-- If this fails, the conversion from "1,500.00" text is wrong, not the processor.
select processor_ref, amount_kobo, fee_kobo, processor_charge_kobo, settled_amount_kobo
from {{ ref('stg_processor_settlement') }}
where settled_amount_kobo <> amount_kobo + fee_kobo - processor_charge_kobo
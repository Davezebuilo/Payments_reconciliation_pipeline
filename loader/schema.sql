-- Raw tables: one per source, every column as text, exactly as the files arrived.
-- The _ columns record where each row came from. Safe to run every time.

CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.ledger (
    merchant_ref text,
    customer_id  text,
    biller_code  text,
    product      text,
    channel      text,
    amount       text,
    fee          text,
    status       text,
    created_at   text,
    _file_date   date        NOT NULL,
    _file_name   text        NOT NULL,
    _row_number  integer     NOT NULL,
    _loaded_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.processor_settlement (
    processor_ref      text,
    merchant_reference text,
    txn_date           text,
    settlement_date    text,
    amount             text,
    fee                text,
    processor_charge   text,
    settled_amount     text,
    status             text,
    _file_date         date        NOT NULL,
    _file_name         text        NOT NULL,
    _row_number        integer     NOT NULL,
    _loaded_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.biller_vends (
    vend_ref         text,
    client_reference text,
    biller_code      text,
    amount_kobo      text,
    token            text,
    vend_status      text,
    vended_at        text,
    _file_date       date        NOT NULL,
    _file_name       text        NOT NULL,
    _row_number      integer     NOT NULL,
    _loaded_at       timestamptz NOT NULL DEFAULT now()
);

-- Loading a day deletes that day first, so _file_date needs an index.
CREATE INDEX IF NOT EXISTS ledger_file_date_idx ON raw.ledger (_file_date);
CREATE INDEX IF NOT EXISTS processor_settlement_file_date_idx ON raw.processor_settlement (_file_date);
CREATE INDEX IF NOT EXISTS biller_vends_file_date_idx ON raw.biller_vends (_file_date);

-- One row per file loaded: the audit trail, and later the source for freshness checks.
CREATE TABLE IF NOT EXISTS raw.load_log (
    id           bigserial PRIMARY KEY,
    source       text        NOT NULL,
    file_date    date        NOT NULL,
    file_name    text        NOT NULL,
    rows_in_file integer     NOT NULL,
    rows_loaded  integer     NOT NULL,
    loaded_at    timestamptz NOT NULL DEFAULT now()
);
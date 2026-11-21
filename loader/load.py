"""Load the landing files into Postgres's raw schema, exactly as they arrived.

Every value is stored as text: the raw layer is a faithful copy, and typing happens later in dbt.
Each day loads in one transaction and replaces whatever was loaded for that day before, so
running it twice never duplicates rows, and a failure part-way leaves nothing half-loaded.

Run:  python -m loader.load --all               (every day in data/landing)
      python -m loader.load --date 2026-10-02   (one day)
"""

from __future__ import annotations

import argparse
import csv
import os
from datetime import date
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql

# The columns each source's file must have, in order. A file that differs is rejected:
# better to stop loudly than to load a changed file into the wrong columns.
SOURCES = {
    "ledger": ["merchant_ref", "customer_id", "biller_code", "product", "channel", "amount", "fee", "status", "created_at"],
    "processor_settlement": [
        "processor_ref",
        "merchant_reference",
        "txn_date",
        "settlement_date",
        "amount",
        "fee",
        "processor_charge",
        "settled_amount",
        "status",
    ],
    "biller_vends": ["vend_ref", "client_reference", "biller_code", "amount_kobo", "token", "vend_status", "vended_at"],
}
SCHEMA_SQL = Path(__file__).with_name("schema.sql")


def connect() -> psycopg.Connection:
    """Connect to the warehouse using the settings in .env."""
    load_dotenv()
    return psycopg.connect(
        host=os.getenv("WAREHOUSE_HOST", "localhost"),
        port=os.getenv("WAREHOUSE_PORT", "5433"),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
    )


def load_file(cur: psycopg.Cursor, source: str, path: Path, file_date: date) -> int:
    """Replace one source's rows for one day with the contents of its file. Returns the row count."""
    table = sql.Identifier("raw", source)
    columns = SOURCES[source]

    with path.open(newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        if header != columns:
            raise ValueError(f"{path}: expected columns {columns}, got {header}")

        cur.execute(sql.SQL("DELETE FROM {} WHERE _file_date = %s").format(table), (file_date,))

        # COPY streams rows into Postgres far faster than one INSERT per row.
        copy_sql = sql.SQL("COPY {} ({}) FROM STDIN").format(
            table, sql.SQL(", ").join(map(sql.Identifier, [*columns, "_file_date", "_file_name", "_row_number"]))
        )
        rows = 0
        with cur.copy(copy_sql) as copy:
            for rows, row in enumerate(reader, start=1):
                copy.write_row([*row, file_date, path.name, rows])

    # Check that everything in the file made it into the table before committing.
    cur.execute(sql.SQL("SELECT count(*) FROM {} WHERE _file_date = %s").format(table), (file_date,))
    loaded = cur.fetchone()[0]
    if loaded != rows:
        raise RuntimeError(f"{path}: file has {rows} rows but {loaded} were loaded")

    cur.execute(
        "INSERT INTO raw.load_log (source, file_date, file_name, rows_in_file, rows_loaded) VALUES (%s, %s, %s, %s, %s)",
        (source, file_date, path.name, rows, loaded),
    )
    return rows


def load_day(conn: psycopg.Connection, folder: Path) -> dict[str, int]:
    """Load every source file in one day's folder, all or nothing."""
    file_date = date.fromisoformat(folder.name)
    counts = {}
    with conn.transaction(), conn.cursor() as cur:
        for source in SOURCES:
            path = folder / f"{source}.csv"
            # Not every day has every file (late settlements arrive after the last ledger day).
            if path.exists():
                counts[source] = load_file(cur, source, path, file_date)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--all", action="store_true", help="load every day in the landing folder")
    which.add_argument("--date", type=date.fromisoformat, help="load one day (YYYY-MM-DD)")
    parser.add_argument("--landing", type=Path, default=Path("data/landing"))
    args = parser.parse_args()

    folders = sorted(p for p in args.landing.iterdir() if p.is_dir()) if args.all else [args.landing / str(args.date)]
    if not folders or not all(f.is_dir() for f in folders):
        raise SystemExit(f"Nothing to load in {args.landing}. Run `make data` first, or check the date.")

    with connect() as conn:
        conn.execute(SCHEMA_SQL.read_text())
        conn.commit()
        for folder in folders:
            counts = load_day(conn, folder)
            print(folder.name, "  ".join(f"{source}: {n:,}" for source, n in counts.items()))


if __name__ == "__main__":
    main()
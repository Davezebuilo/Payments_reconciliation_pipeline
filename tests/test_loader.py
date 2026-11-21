"""Loader tests. They need the warehouse running (`make up`) and are skipped otherwise.

They load a tiny dataset dated 2099, far from the real data, and delete it afterwards.
"""

from datetime import date
from pathlib import Path

import numpy as np
import psycopg
import pytest
import yaml

from generator.generate import build_ledger, build_settlements, build_vends, inject_anomalies, write_files
from loader.load import SCHEMA_SQL, SOURCES, connect, load_day

CONFIG = Path(__file__).parents[1] / "generator" / "config.yaml"
START = date(2099, 1, 1)


@pytest.fixture(scope="module")
def conn():
    try:
        conn = connect()
    except (psycopg.OperationalError, KeyError):
        pytest.skip("warehouse isn't running (start it with `make up`)")
    conn.execute(SCHEMA_SQL.read_text())
    conn.commit()
    yield conn
    for table in [*SOURCES, "load_log"]:
        column = "file_date" if table == "load_log" else "_file_date"
        conn.execute(f"DELETE FROM raw.{table} WHERE {column} >= %s", (START,))
    conn.commit()
    conn.close()


@pytest.fixture(scope="module")
def landing(tmp_path_factory):
    cfg = yaml.safe_load(CONFIG.read_text())
    cfg["transactions_per_day"] = 500
    rng = np.random.default_rng(cfg["seed"])
    ledger = build_ledger(cfg, rng, START, 2)
    paid = ledger[ledger["status"].eq("successful")]
    settlements, vends, _ = inject_anomalies(ledger, build_settlements(paid, cfg), build_vends(paid, rng), cfg, rng)
    folder = tmp_path_factory.mktemp("landing")
    write_files(ledger, settlements, vends, folder)
    return folder


def file_rows(path: Path) -> int:
    return sum(1 for _ in path.open()) - 1  # minus the header


def table_rows(conn, source: str, day: date) -> int:
    return conn.execute(f"SELECT count(*) FROM raw.{source} WHERE _file_date = %s", (day,)).fetchone()[0]


def test_every_row_in_the_file_is_loaded(conn, landing):
    folder = landing / str(START)
    counts = load_day(conn, folder)
    for source, n in counts.items():
        assert n == file_rows(folder / f"{source}.csv") == table_rows(conn, source, START)


def test_loading_a_day_twice_does_not_duplicate(conn, landing):
    folder = landing / str(START)
    load_day(conn, folder)
    first = {s: table_rows(conn, s, START) for s in SOURCES}
    load_day(conn, folder)
    assert {s: table_rows(conn, s, START) for s in SOURCES} == first


def test_a_bad_file_leaves_the_day_untouched(conn, landing, tmp_path):
    # The second day has all three files (the first has no settlements yet: they arrive T+1).
    day = date(2099, 1, 2)
    folder = landing / str(day)
    load_day(conn, folder)
    before = {s: table_rows(conn, s, day) for s in SOURCES}
    assert all(before.values())

    # Same day, but the vends file (loaded last) has a renamed column.
    broken = tmp_path / str(day)
    broken.mkdir()
    for path in folder.glob("*.csv"):
        text = path.read_text()
        if path.stem == "biller_vends":
            text = text.replace("vend_status", "status", 1)
        (broken / path.name).write_text(text)

    with pytest.raises(ValueError, match="expected columns"):
        load_day(conn, broken)
    # The ledger and settlements were reloaded before the vends file failed, then rolled back.
    assert {s: table_rows(conn, s, day) for s in SOURCES} == before
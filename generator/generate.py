"""Generate synthetic payments data for the reconciliation pipeline.

For every day it writes the three files the sources would deliver:
  ledger.csv                the platform's own record of every payment (clean, Lagos time)
  processor_settlement.csv  what the payment processor settled (naira strings, dd/mm/yyyy dates)
  biller_vends.csv          what the biller actually vended (kobo integers, UTC times)
plus ground_truth.csv, which lists every error it injected so the pipeline can be checked.

Run:  python -m generator.generate --start 2026-10-01 --days 30
"""

from __future__ import annotations

import argparse
import shutil
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

TZ = "Africa/Lagos"

# Errors that each hit one existing successful transaction. Every transaction gets at most one.
PER_TRANSACTION = [
    "missing_settlement",
    "missing_vend",
    "vend_failed",
    "amount_mismatch",
    "fee_mismatch",
    "duplicate_settlement",
    "duplicate_vend",
    "late_settlement",
    "missing_reference",
    "wrong_biller",
]


def build_ledger(cfg: dict, rng: np.random.Generator, start: date, days: int) -> pd.DataFrame:
    """One row per payment attempt, for every day in the range."""
    billers = pd.DataFrame(cfg["billers"])
    n = cfg["transactions_per_day"]
    frames = []
    for d in range(days):
        day = start + timedelta(days=d)
        b = billers.iloc[rng.integers(0, len(billers), n)].reset_index(drop=True)
        # Round amounts to the nearest ₦50, like real top-ups.
        naira = rng.integers(b["min"].to_numpy(), b["max"].to_numpy() + 1) // 50 * 50
        seconds = np.sort(rng.integers(0, 86_400, n))
        frames.append(
            pd.DataFrame(
                {
                    "merchant_ref": [f"PRX-{day:%Y%m%d}-{i:07d}" for i in range(1, n + 1)],
                    "customer_id": [f"CUS{c:07d}" for c in rng.integers(1, 2_000_000, n)],
                    "biller_code": b["code"],
                    "product": b["product"],
                    "channel": rng.choice(list(cfg["channels"]), n, p=list(cfg["channels"].values())),
                    "amount": naira.astype(float),
                    "created_at": pd.Timestamp(day.isoformat(), tz=TZ) + pd.to_timedelta(seconds, unit="s"),
                    "status": rng.choice(list(cfg["statuses"]), n, p=list(cfg["statuses"].values())),
                }
            )
        )
    ledger = pd.concat(frames, ignore_index=True)
    ledger["fee"] = np.minimum((ledger["amount"] * cfg["fee"]["percent"]).round(2), cfg["fee"]["cap"])
    return ledger


def build_settlements(ledger: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """What the processor settles: every successful payment, the next day (T+1)."""
    s = pd.DataFrame(
        {
            "merchant_reference": ledger["merchant_ref"],
            # Midnight of the payment's Lagos date, as a plain date-time.
            "txn_date": ledger["created_at"].dt.tz_localize(None).dt.normalize(),
            "amount": ledger["amount"],
            "fee": ledger["fee"],
            "status": "settled",
        }
    )
    s["settlement_date"] = s["txn_date"] + pd.Timedelta(days=1)
    charge = cfg["processor_charge"]
    s["processor_charge"] = np.minimum(((s["amount"] + s["fee"]) * charge["percent"]).round(2), charge["cap"])
    return s


def tokens(rng: np.random.Generator, n: int) -> list[str]:
    """20-digit electricity tokens."""
    return [f"{a:010d}{b:010d}" for a, b in zip(rng.integers(0, 10**10, n), rng.integers(0, 10**10, n))]


def build_vends(ledger: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """What the biller vends: every successful payment, 1 to 180 seconds after it was made."""
    v = pd.DataFrame(
        {
            "client_reference": ledger["merchant_ref"],
            "biller_code": ledger["biller_code"],
            "amount_kobo": (ledger["amount"] * 100).round().astype("int64"),
            "vended_at": ledger["created_at"] + pd.to_timedelta(rng.integers(1, 181, len(ledger)), unit="s"),
            "vend_status": "success",
        }
    )
    # Only electricity comes with a token; airtime and data don't.
    v["token"] = np.where(ledger["product"].eq("electricity"), tokens(rng, len(v)), "")
    return v


def inject_anomalies(
    ledger: pd.DataFrame, settlements: pd.DataFrame, vends: pd.DataFrame, cfg: dict, rng: np.random.Generator
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Break things on purpose, and record exactly what was broken in a ground-truth table."""
    rates = cfg["anomalies"]
    truth: list[pd.DataFrame] = []

    def record(kind: str, refs) -> None:
        truth.append(pd.DataFrame({"merchant_ref": list(refs), "anomaly": kind}))

    # Hand each error type its own slice of shuffled successful transactions, so none overlap.
    paid = rng.permutation(ledger.index[ledger["status"].eq("successful")].to_numpy())
    picks, pos = {}, 0
    for kind in PER_TRANSACTION:
        k = int(len(paid) * rates[kind])
        picks[kind] = paid[pos : pos + k]
        pos += k
        record(kind, ledger.loc[picks[kind], "merchant_ref"])

    # Settlements and vends share the ledger's index, so a ledger row's label finds its partners.
    settlements = settlements.drop(picks["missing_settlement"])
    vends = vends.drop(picks["missing_vend"])

    i = picks["vend_failed"]
    vends.loc[i, "vend_status"] = "failed"
    vends.loc[i, "token"] = ""

    i = picks["wrong_biller"]
    codes = [b["code"] for b in cfg["billers"]]
    # Shift each code to the next biller in the list (the last wraps to the first), so it always differs.
    next_code = dict(zip(codes, codes[1:] + codes[:1]))
    vends.loc[i, "biller_code"] = vends.loc[i, "biller_code"].map(next_code)

    i = picks["amount_mismatch"]
    delta = rng.choice([-1, 1], len(i)) * rng.integers(1, 11, len(i)) * 50
    settlements.loc[i, "amount"] = np.maximum(settlements.loc[i, "amount"] + delta, 50)

    i = picks["fee_mismatch"]
    settlements.loc[i, "fee"] = settlements.loc[i, "fee"] + rng.integers(1, 10, len(i)) * 10

    i = picks["late_settlement"]
    settlements.loc[i, "settlement_date"] += pd.to_timedelta(rng.integers(1, 5, len(i)), unit="D")

    settlements.loc[picks["missing_reference"], "merchant_reference"] = ""

    settlements = pd.concat([settlements, settlements.loc[picks["duplicate_settlement"]]])

    dup = vends.loc[picks["duplicate_vend"]].copy()
    dup["vended_at"] += pd.to_timedelta(rng.integers(30, 600, len(dup)), unit="s")
    dup["token"] = np.where(dup["token"].eq(""), "", tokens(rng, len(dup)))
    vends = pd.concat([vends, dup])

    # Failed in the ledger, yet the processor settled it.
    failed = ledger.index[ledger["status"].eq("failed")].to_numpy()
    i = rng.choice(failed, int(len(failed) * rates["status_mismatch"]), replace=False)
    settlements = pd.concat([settlements, build_settlements(ledger.loc[i], cfg)])
    record("status_mismatch", ledger.loc[i, "merchant_ref"])

    # Vends for payments the ledger never saw: copy real vends and give them unknown references.
    k = int(len(paid) * rates["orphan_vend"])
    orphans = vends.sample(k, random_state=rng).copy()
    orphans["client_reference"] = [
        f"{ref[:13]}9{n:06d}" for ref, n in zip(orphans["client_reference"], rng.integers(0, 10**6, k))
    ]
    vends = pd.concat([vends, orphans])
    record("orphan_vend", orphans["client_reference"])

    return settlements, vends, pd.concat(truth, ignore_index=True)


def naira(series: pd.Series) -> pd.Series:
    """1500.0 → '1,500.00', the way the processor's file shows money."""
    return series.map("{:,.2f}".format)


def write_files(ledger: pd.DataFrame, settlements: pd.DataFrame, vends: pd.DataFrame, landing: Path) -> None:
    """Write each source's rows into the folder for the day its file would arrive."""
    settlements = settlements.reset_index(drop=True)
    vends = vends.reset_index(drop=True)

    ledger_out = ledger.assign(
        file_date=ledger["created_at"].dt.date,
        created_at=ledger["created_at"].dt.strftime("%Y-%m-%dT%H:%M:%S%z"),
    )[["merchant_ref", "customer_id", "biller_code", "product", "channel", "amount", "fee", "status", "created_at", "file_date"]]

    settled = settlements["amount"] + settlements["fee"] - settlements["processor_charge"]
    processor_out = pd.DataFrame(
        {
            "processor_ref": [f"PYR{i:010d}" for i in range(1, len(settlements) + 1)],
            "merchant_reference": settlements["merchant_reference"],
            "txn_date": settlements["txn_date"].dt.strftime("%d/%m/%Y"),
            "settlement_date": settlements["settlement_date"].dt.strftime("%d/%m/%Y"),
            "amount": naira(settlements["amount"]),
            "fee": naira(settlements["fee"]),
            "processor_charge": naira(settlements["processor_charge"]),
            "settled_amount": naira(settled),
            "status": settlements["status"],
            "file_date": settlements["settlement_date"].dt.date,
        }
    )

    vends_out = pd.DataFrame(
        {
            "vend_ref": [f"VND{i:010d}" for i in range(1, len(vends) + 1)],
            "client_reference": vends["client_reference"],
            "biller_code": vends["biller_code"],
            "amount_kobo": vends["amount_kobo"],
            "token": vends["token"],
            "vend_status": vends["vend_status"],
            "vended_at": vends["vended_at"].dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            # The biller's day is still Lagos time, so a vend just after midnight lands in the next file.
            "file_date": vends["vended_at"].dt.date,
        }
    )

    for name, frame in [("ledger", ledger_out), ("processor_settlement", processor_out), ("biller_vends", vends_out)]:
        for day, rows in frame.groupby("file_date"):
            folder = landing / str(day)
            folder.mkdir(parents=True, exist_ok=True)
            rows.drop(columns="file_date").to_csv(folder / f"{name}.csv", index=False, float_format="%.2f")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 10, 1), help="first day (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=30, help="how many days of transactions")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.yaml"))
    parser.add_argument("--out", type=Path, default=Path("data"), help="output folder")
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text())
    rng = np.random.default_rng(cfg["seed"])

    ledger = build_ledger(cfg, rng, args.start, args.days)
    paid = ledger[ledger["status"].eq("successful")]
    settlements, vends, truth = inject_anomalies(ledger, build_settlements(paid, cfg), build_vends(paid, rng), cfg, rng)

    landing = args.out / "landing"
    shutil.rmtree(landing, ignore_errors=True)  # start clean so old files never mix in
    write_files(ledger, settlements, vends, landing)
    truth.to_csv(args.out / "ground_truth.csv", index=False)

    print(f"ledger: {len(ledger):,}  settlements: {len(settlements):,}  vends: {len(vends):,}")
    print(f"injected errors: {len(truth):,}")
    print(truth["anomaly"].value_counts().to_string())


if __name__ == "__main__":
    main()
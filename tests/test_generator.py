"""The ground truth must describe the generated data exactly, or the pipeline can't be graded."""

from datetime import date
from pathlib import Path

import numpy as np
import pytest
import yaml

from generator.generate import build_ledger, build_settlements, build_vends, inject_anomalies

CONFIG = Path(__file__).parents[1] / "generator" / "config.yaml"


@pytest.fixture(scope="module")
def data():
    cfg = yaml.safe_load(CONFIG.read_text())
    cfg["transactions_per_day"] = 5_000  # small and fast
    rng = np.random.default_rng(cfg["seed"])
    ledger = build_ledger(cfg, rng, date(2026, 10, 1), 3)
    paid = ledger[ledger["status"].eq("successful")]
    settlements, vends, truth = inject_anomalies(ledger, build_settlements(paid, cfg), build_vends(paid, rng), cfg, rng)
    return ledger, settlements, vends, truth


def refs(truth, kind):
    return set(truth.loc[truth["anomaly"].eq(kind), "merchant_ref"])


def test_ledger_references_are_unique(data):
    ledger, *_ = data
    assert ledger["merchant_ref"].is_unique


def test_each_transaction_has_at_most_one_error(data):
    *_, truth = data
    assert truth["merchant_ref"].is_unique


def test_missing_settlements_are_missing(data):
    _, settlements, _, truth = data
    assert refs(truth, "missing_settlement").isdisjoint(settlements["merchant_reference"])


def test_missing_vends_are_missing(data):
    _, _, vends, truth = data
    assert refs(truth, "missing_vend").isdisjoint(vends["client_reference"])


def test_orphan_vends_have_no_ledger_transaction(data):
    ledger, _, vends, truth = data
    orphans = refs(truth, "orphan_vend")
    assert orphans and orphans.isdisjoint(ledger["merchant_ref"])
    assert orphans <= set(vends["client_reference"])


def test_status_mismatches_failed_in_the_ledger_but_were_settled(data):
    ledger, settlements, _, truth = data
    mismatched = refs(truth, "status_mismatch")
    assert set(ledger.loc[ledger["merchant_ref"].isin(mismatched), "status"]) == {"failed"}
    assert mismatched <= set(settlements["merchant_reference"])


def test_clean_transactions_match_exactly_once(data):
    ledger, settlements, vends, truth = data
    clean = set(ledger.loc[ledger["status"].eq("successful"), "merchant_ref"]) - set(truth["merchant_ref"])
    settled = settlements["merchant_reference"].value_counts()
    vended = vends["client_reference"].value_counts()
    assert (settled.reindex(list(clean)) == 1).all()
    assert (vended.reindex(list(clean)) == 1).all()

def test_wrong_biller_vends_show_a_different_biller(data):
    ledger, _, vends, truth = data
    wrong = list(refs(truth, "wrong_biller"))
    in_ledger = ledger.set_index("merchant_ref").loc[wrong, "biller_code"]
    in_vends = vends.set_index("client_reference").loc[wrong, "biller_code"]
    assert wrong and (in_ledger != in_vends).all()
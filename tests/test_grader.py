"""The grader's maths, on a tiny made-up example (no warehouse needed)."""

import pandas as pd

from grader.grade import score


def test_score_counts_hits_misses_and_reviews():
    truth = pd.DataFrame({"merchant_ref": ["A", "B", "C", "D"], "anomaly": ["missing_vend", "missing_vend", "fee_mismatch", "fee_mismatch"]})
    found = pd.DataFrame({"merchant_ref": ["A", "B", "C", "E"], "found": ["missing_vend", "needs_review", "fee_mismatch", "fee_mismatch"]})
    report = score(truth, found)

    vend = report.loc["missing_vend"]
    assert (vend["correct"], vend["review"], vend["recall"], vend["caught"]) == (1, 1, 0.5, 1.0)

    fee = report.loc["fee_mismatch"]  # caught C, missed D, falsely flagged E
    assert (fee["precision"], fee["recall"], fee["caught"]) == (0.5, 0.5, 0.5)
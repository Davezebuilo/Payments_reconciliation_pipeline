"""Grade the pipeline against the generator's answer key.

For each kind of error: how many were injected, how many the pipeline named correctly
(recall), how many of its flags were right (precision), and how many it sent to a person
because the data couldn't settle it (review). Exits with an error if any flag is wrong or
any error slips through unflagged, so it can gate CI.

Run:  python -m grader.grade
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from loader.load import connect

TRUTH = Path("data/ground_truth.csv")
MIN_PRECISION = 1.0   # every flag must be right: a false alarm sends finance chasing nothing
MIN_CAUGHT = 1.0      # every real error must be either named or sent for review, never missed


def flagged() -> pd.DataFrame:
    """Every transaction the pipeline says has a problem."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT merchant_ref, recon_status FROM marts.fct_reconciliation "
            "WHERE recon_status NOT IN ('matched', 'not_applicable')"
        ).fetchall()
    return pd.DataFrame(rows, columns=["merchant_ref", "found"])


def score(truth: pd.DataFrame, found: pd.DataFrame) -> pd.DataFrame:
    both = truth.merge(found, on="merchant_ref", how="outer")
    rows = []
    review = both["found"].eq("needs_review")
    for kind in sorted(set(truth["anomaly"]) | set(found["found"]) - {"needs_review"}):
        injected = both["anomaly"].eq(kind)
        flagged = both["found"].eq(kind)
        right = (injected & flagged).sum()
        sent = (injected & review).sum()
        rows.append(
            {
                "anomaly": kind,
                "injected": injected.sum(),
                "flagged": flagged.sum(),
                "correct": right,
                "review": sent,
                "precision": right / flagged.sum() if flagged.any() else 1.0,
                "recall": right / injected.sum() if injected.any() else 1.0,
                "caught": (right + sent) / injected.sum() if injected.any() else 1.0,
            }
        )
    return pd.DataFrame(rows).set_index("anomaly")


def main() -> None:
    truth, found = pd.read_csv(TRUTH), flagged()
    report = score(truth, found)
    pct = "{:.2%}".format
    print(report.to_string(formatters={"precision": pct, "recall": pct, "caught": pct}))

    review = found.loc[found["found"].eq("needs_review"), "merchant_ref"]
    clean = (~review.isin(truth["merchant_ref"])).sum()
    print(f"\nSent for review: {len(review):,} ({clean:,} of them had nothing wrong)")

    failing = report[(report["precision"] < MIN_PRECISION) | (report["caught"] < MIN_CAUGHT)]
    if not failing.empty or clean:
        sys.exit(f"\nBelow the bar: {', '.join(failing.index) or 'clean payments sent for review'}")
    print("Every flag is right, and no error slipped through.")


if __name__ == "__main__":
    main()
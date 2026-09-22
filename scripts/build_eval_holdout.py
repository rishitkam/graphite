"""Carve the labeled eval sets out of closed_cases_history.csv.

Two slices, both held out from retrieval memory during eval:

matched: cleared cases paired with confirmed fraud at nearly the same risk
  score. The bank only opened cases on legitimate transactions when the
  model scored them high (0.82 to 0.96), while fraud was opened by customer
  reports at any score. Unmatched, "high score means cleared" gets 91%
  accuracy on its own, so the eval would measure that artifact instead of
  investigation quality. Matching removes it.

rare_patterns: card testing and undocumented cases, too rare to match on
  score. Graded only on whether the pattern is identified.
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "eval" / "holdout_case_ids.json"

N_MATCHED = 80
SCORE_TOLERANCE = 0.01
RARE = {"card_testing": 5, "undocumented": 3}
SEED = 42


def flagged_scores(cases):
    tx = pd.read_parquet(DATA / "tx_slim.parquet", columns=["TransactionID", "risk_score"])
    score = tx.set_index("TransactionID")["risk_score"].astype(float)
    flag = cases["first_fraud_txn_id"].fillna(cases["txn_ids"].str.split("|").str[0])
    return score.loc[flag].to_numpy()


def matched_slice(cases):
    cleared = cases[cases["outcome"] == "cleared"].sample(n=N_MATCHED, random_state=SEED)
    fraud = cases[(cases["outcome"] == "confirmed_fraud") & ~cases["pattern"].isin(RARE)]
    fraud = fraud.sample(frac=1, random_state=SEED)

    picked = []
    used = set()
    for s in cleared["score"].sort_values():
        pool = fraud[~fraud.index.isin(used) & ((fraud["score"] - s).abs() <= SCORE_TOLERANCE)]
        if pool.empty:
            raise SystemExit(f"no fraud case within {SCORE_TOLERANCE} of score {s:.2f}")
        pick = (pool["score"] - s).abs().idxmin()
        used.add(pick)
        picked.append(pick)
    return pd.concat([cleared, fraud.loc[picked]])


def rare_slice(cases):
    fraud = cases[cases["outcome"] == "confirmed_fraud"]
    return pd.concat(
        fraud[fraud["pattern"] == p].sample(n=n, random_state=SEED) for p, n in RARE.items()
    )


def rows(df, slice_name):
    return [
        {"case_id": r.case_id, "slice": slice_name, "outcome": r.outcome,
         "pattern": r.pattern, "flagged_score": round(r.score, 2)}
        for r in df.sort_values("case_id").itertuples()
    ]


def main():
    cases = pd.read_csv(DATA / "closed_cases_history.csv", dtype=str)
    cases["score"] = flagged_scores(cases)

    matched = matched_slice(cases)
    rare = rare_slice(cases)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "seed": SEED,
        "score_tolerance": SCORE_TOLERANCE,
        "source": "data/closed_cases_history.csv",
        "cases": rows(matched, "matched") + rows(rare, "rare_patterns"),
    }, indent=2) + "\n")

    print(f"matched: {len(matched)}  rare_patterns: {len(rare)}")
    print(matched.groupby("outcome")["score"].describe()[["mean", "min", "max"]].round(3).to_string())
    print(matched.groupby(["outcome", "pattern"]).size().to_string())


if __name__ == "__main__":
    main()

"""One input format for every pipeline: an Alert.

Exam alerts come straight from case_pack.csv. Eval alerts are rebuilt from
held-out closed cases, with the trigger neutralised: in the closed cases,
every confirmed fraud was a customer report and every cleared case was a
model score, so passing the real trigger through would hand every pipeline
the label for free.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
HOLDOUT = ROOT / "eval" / "holdout_case_ids.json"


@dataclass
class Alert:
    case_id: str
    opened_at: str
    trigger_type: str
    trigger_text: str
    flagged_txn_id: str
    card_id: str
    customer_id: str
    risk_score: float | None
    label: str | None = None  # eval only: "fraud" or "legitimate"
    label_pattern: str | None = None
    eval_slice: str | None = None


def exam_alerts():
    cp = pd.read_csv(DATA / "case_pack.csv", dtype=str)
    return [
        Alert(
            case_id=r.case_id, opened_at=r.opened_at, trigger_type=r.trigger_type,
            trigger_text=r.trigger_text, flagged_txn_id=r.flagged_txn_id,
            card_id=r.card_id, customer_id=r.customer_id,
            risk_score=float(r.risk_score) if isinstance(r.risk_score, str) else None,
        )
        for r in cp.itertuples()
    ]


def holdout():
    return {c["case_id"]: c["slice"] for c in json.loads(HOLDOUT.read_text())["cases"]}


def holdout_ids():
    return set(holdout())


def eval_alerts():
    cc = pd.read_csv(DATA / "closed_cases_history.csv", dtype=str)
    slices = holdout()
    cc = cc[cc["case_id"].isin(slices)]
    tx = pd.read_parquet(DATA / "tx_slim.parquet", columns=["TransactionID", "TransactionAmt", "risk_score"])
    tx = tx.set_index("TransactionID")

    alerts = []
    for r in cc.itertuples():
        txn = r.first_fraud_txn_id if isinstance(r.first_fraud_txn_id, str) else r.txn_ids.split("|")[0]
        amt = float(tx.at[txn, "TransactionAmt"])
        score = float(tx.at[txn, "risk_score"])
        alerts.append(Alert(
            case_id=r.case_id, opened_at=r.opened_at, trigger_type="alert",
            trigger_text=f"Transaction {txn} (${amt:,.2f}) on card {r.card_id} was flagged for review. Model risk score {score:.2f}. Review and decide.",
            flagged_txn_id=txn, card_id=r.card_id, customer_id=r.customer_id,
            risk_score=score,
            label="fraud" if r.outcome == "confirmed_fraud" else "legitimate",
            label_pattern=r.pattern,
            eval_slice=slices[r.case_id],
        ))
    return alerts

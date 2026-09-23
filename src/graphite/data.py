"""Local lookups shared by every tier.

alert_record is the flagged transaction itself, which is part of the alert,
so the RAG tier may see it without touching the graph. amounts is only used
after the model has answered, to price the transactions it named.
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

LOAD = Path(__file__).resolve().parents[2] / "data" / "load"


@lru_cache(maxsize=1)
def _tx():
    tx = pd.read_csv(LOAD / "transactions.csv", dtype={"txn_id": str, "addr1": str}).set_index("txn_id")
    dev = pd.read_csv(LOAD / "tx_device.csv", dtype=str).set_index("txn_id")
    email = pd.read_csv(LOAD / "tx_email.csv", dtype=str).set_index("txn_id")
    return tx.join(dev).join(email)


@lru_cache(maxsize=1)
def amounts():
    return _tx()["amount"].astype(float).to_dict()


def alert_record(txn_id):
    r = _tx().loc[txn_id]
    rec = {
        "txn_id": txn_id, "card_id": r.card_id, "amount": float(r.amount), "ts": r.ts,
        "product_cd": r.product_cd, "channel": r.channel, "risk_score": float(r.risk_score),
        "billing_region": r.addr1, "email_domain": r.domain, "device": r.device_key,
        "device_seen": r.device_seen, "proxy": r.proxy_type,
    }
    return {k: v for k, v in rec.items() if isinstance(v, (int, float, str)) and v == v}


@lru_cache(maxsize=1)
def closed_cases():
    return pd.read_csv(Path(__file__).resolve().parents[2] / "data" / "closed_cases_history.csv", dtype=str)


@lru_cache(maxsize=1)
def _first_seen():
    tx = _tx()
    customers = tx["card_id"].str.split("-").str[0]
    return pd.to_datetime(tx["ts"]).groupby(customers).min().sort_values().to_numpy()


def customers_per_fraud_case(t_end, exclude):
    """Bank-wide: active customers per confirmed fraud case, as of t_end.

    Gives the model a base rate, so "5 fraud cases on this device" can be
    read against how common fraud cases are anyway.
    """
    t = pd.Timestamp(t_end)
    active = int(_first_seen().searchsorted(t.to_datetime64(), side="right"))
    cc = closed_cases()
    n = int(((cc["outcome"] == "confirmed_fraud") & (pd.to_datetime(cc["closed_at"]) < t)
             & ~cc["case_id"].isin(exclude)).sum())
    return active / n if n else None


def memory_fraud_share(t_end, exclude):
    """Share of case memory that is confirmed fraud, as of t_end.

    Case memory is a record of what the bank chose to investigate, not of how
    often fraud happens: legitimate transactions were only investigated when
    the bank's model flagged them. So memory is read relative to this.
    """
    cc = closed_cases()
    pool = cc[(pd.to_datetime(cc["closed_at"]) < pd.Timestamp(t_end)) & ~cc["case_id"].isin(exclude)]
    return float((pool["outcome"] == "confirmed_fraud").mean()) if len(pool) else None

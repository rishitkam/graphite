"""The graph context of an alert, as a fixed-length vector.

Every closed case gets one, computed as of its own alert time, and it is
stored on the ClosedCase vertex in TigerGraph's vector index. A new alert's
vector then retrieves the past alerts that were in the most similar
situation, and how they ended. That's case memory keyed on what the graph
looked like, not on how the notes happen to be worded.

One function computes both the stored vectors and the live query, so they
can't drift apart. Nothing after the as-of time is ever read.
"""

from bisect import bisect_right
from functools import lru_cache

import numpy as np
import pandas as pd

from graphite import data

FEATURES = [
    "online", "has_device", "device_new", "proxy", "device_uses_on_card", "device_customers",
    "region_share", "product_share", "email_share", "amount_vs_avg", "history_len",
    "txns_72h_before", "small_auths_1h", "txns_after", "risk_score",
]
AFTER_WINDOW = pd.Timedelta(hours=6)


@lru_cache(maxsize=1)
def _frames():
    tx = data._tx().reset_index().rename(columns={"index": "txn_id"})
    tx["ts"] = pd.to_datetime(tx["ts"])
    tx["amount"] = tx["amount"].astype(float)
    tx = tx.sort_values(["card_id", "ts"])
    by_card = {k: g.reset_index(drop=True) for k, g in tx.groupby("card_id", sort=False)}
    dev = tx.dropna(subset=["device_key"])
    dev = dev.assign(customer=dev["card_id"].str.split("-").str[0])
    first_use = dev.groupby(["device_key", "customer"])["ts"].min().reset_index()
    dev_first = {k: np.sort(g["ts"].to_numpy()) for k, g in first_use.groupby("device_key")}
    return tx.set_index("txn_id"), by_card, dev_first


def features(txn_id, t_end):
    tx, by_card, dev_first = _frames()
    f = tx.loc[txn_id]
    t0, t_end = f.ts, pd.Timestamp(t_end)
    card = by_card[f.card_id]
    before = card[card.ts < t0]
    n = len(before)
    after = card[(card.ts > t0) & (card.ts <= min(t_end, t0 + AFTER_WINDOW))]
    recent = before[before.ts >= t0 - pd.Timedelta(hours=72)]
    hour = before[(before.ts >= t0 - pd.Timedelta(hours=1)) & (before.channel == "online") & (before.amount < 5)]
    dev = f.device_key if isinstance(f.device_key, str) else None

    def share(col, val):
        return (before[col] == val).sum() / n if n and isinstance(val, str) else 0.0

    return {
        "online": float(f.channel == "online"),
        "has_device": float(dev is not None),
        "device_new": float(f.device_seen == "New"),
        "proxy": float(isinstance(f.proxy_type, str)),
        "device_uses_on_card": np.log1p((before.device_key == dev).sum()) if dev else 0.0,
        "device_customers": np.log1p(bisect_right(dev_first[dev], t_end.to_datetime64())) if dev else 0.0,
        "region_share": share("addr1", f.addr1),
        "product_share": share("product_cd", f.product_cd),
        "email_share": share("domain", f.domain),
        "amount_vs_avg": np.log(f.amount / before.amount.mean()) if n and before.amount.mean() > 0 else 0.0,
        "history_len": np.log1p(n),
        "txns_72h_before": np.log1p(len(recent)),
        "small_auths_1h": np.log1p(len(hour)),
        "txns_after": np.log1p(len(after)),
        "risk_score": float(f.risk_score),
    }


def vector(txn_id, t_end, stats):
    v = np.array([features(txn_id, t_end)[k] for k in FEATURES], dtype=np.float64)
    return ((v - stats["mean"]) / stats["std"]).astype(np.float32)


def describe(txn_id, t_end):
    """The same features as readable facts, for the evidence pack."""
    x = features(txn_id, t_end)
    return (f"online={int(x['online'])} device_new={int(x['device_new'])} proxy={int(x['proxy'])} "
            f"region_share={x['region_share']:.2f} product_share={x['product_share']:.2f} "
            f"amount_vs_avg={np.exp(x['amount_vs_avg']):.1f}x history={int(np.expm1(x['history_len']))} "
            f"txns_72h_before={int(np.expm1(x['txns_72h_before']))} txns_after={int(np.expm1(x['txns_after']))}")

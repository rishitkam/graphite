"""Compute the situation vector for every closed case, as of its own alert time.

Alert time is six hours after the flagged transaction, the same window the
dev and eval alerts use. Standardisation stats come from the memory pool
only (never from held-out cases), and are saved so live queries use the
same scale.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from graphite import alerts, data, situation

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "situations.npz"


def main():
    cc = data.closed_cases()
    flag = cc["first_fraud_txn_id"].fillna(cc["txn_ids"].str.split("|").str[0])
    ts = pd.to_datetime(data._tx().loc[flag, "ts"].to_numpy())
    t_alert = ts + situation.AFTER_WINDOW

    raw = np.array([[situation.features(t, str(a))[k] for k in situation.FEATURES]
                    for t, a in zip(flag, t_alert)], dtype=np.float64)

    held = cc["case_id"].isin(alerts.holdout_ids()).to_numpy()
    mean, std = raw[~held].mean(0), raw[~held].std(0) + 1e-6
    np.savez(OUT, case_ids=cc["case_id"].to_numpy(), vectors=((raw - mean) / std).astype(np.float32),
             mean=mean, std=std, features=np.array(situation.FEATURES))
    (ROOT / "eval" / "situation_scaling.json").write_text(json.dumps(
        {"features": situation.FEATURES, "mean": mean.tolist(), "std": std.tolist()}, indent=1))
    print(f"{len(cc)} situation vectors, {len(situation.FEATURES)} features -> {OUT.relative_to(ROOT)}")

    pool = ~held
    lab = (cc["outcome"] == "confirmed_fraud").to_numpy()
    print("memory pool feature means (fraud vs cleared):")
    for i, k in enumerate(situation.FEATURES):
        print(f"  {k:<20} {raw[pool & lab, i].mean():8.3f} {raw[pool & ~lab, i].mean():8.3f}")


if __name__ == "__main__":
    main()

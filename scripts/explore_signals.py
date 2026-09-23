"""Which evidence separates fraud from false alarms once risk score is neutral?

Runs on the memory pool only (closed cases NOT in the eval holdout), so
nothing about the pipelines gets designed against the eval set. Compares
confirmed fraud against cleared cases at similar risk scores, using only
information available at the time the case was opened.
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

holdout = {c["case_id"] for c in json.loads((ROOT / "eval" / "holdout_case_ids.json").read_text())["cases"]}

tx = pd.read_csv(DATA / "load" / "transactions.csv", dtype={"txn_id": str}, parse_dates=["ts"])
dev = pd.read_csv(DATA / "load" / "tx_device.csv", dtype=str)
email = pd.read_csv(DATA / "load" / "tx_email.csv", dtype=str)
tx = tx.merge(dev, on="txn_id", how="left").merge(email, on="txn_id", how="left")
tx["customer_id"] = tx["card_id"].str.split("-").str[0]
tx = tx.sort_values("ts")

cc = pd.read_csv(DATA / "closed_cases_history.csv", dtype=str)
cc = cc[~cc["case_id"].isin(holdout)]
cc["flag"] = cc["first_fraud_txn_id"].fillna(cc["txn_ids"].str.split("|").str[0])
cc = cc.merge(tx.add_prefix("f_"), left_on="flag", right_on="f_txn_id")
cc = cc[cc["f_risk_score"] >= 0.80]  # score band where cleared cases live

by_card = {k: g for k, g in tx.groupby("card_id")}
by_cust = {k: g for k, g in tx.groupby("customer_id")}
dev_customers = dev.merge(tx[["txn_id", "customer_id"]], on="txn_id").groupby("device_key")["customer_id"].nunique()


def features(r):
    t0 = r.f_ts
    card = by_card[r.card_id]
    hist = card[card.ts < t0]
    cust_hist = by_cust[r.customer_id]
    cust_hist = cust_hist[cust_hist.ts < t0]
    near = card[(card.ts >= t0 - pd.Timedelta(hours=48)) & (card.ts <= t0)]
    med = hist.TransactionAmt.median() if "TransactionAmt" in hist else hist.amount.median()
    return {
        "outcome": r.outcome,
        "channel": r.f_channel,
        "device_new": r.f_device_seen == "New",
        "proxy": isinstance(r.f_proxy_type, str),
        "region_new_for_customer": isinstance(r.f_addr1, str) and r.f_addr1 not in set(cust_hist.addr1.dropna()),
        "product_new_for_card": r.f_product_cd not in set(hist.product_cd),
        "email_new_for_card": isinstance(r.f_domain, str) and r.f_domain not in set(hist.domain.dropna()),
        "device_new_for_card": isinstance(r.f_device_key, str) and r.f_device_key not in set(hist.device_key.dropna()),
        "amount_vs_median": r.f_amount / med if med and med > 0 else None,
        "txns_48h": len(near),
        "history_len": len(hist),
        "device_shared_customers": dev_customers.get(r.f_device_key, 0) if isinstance(r.f_device_key, str) else 0,
    }


def main():
    f = pd.DataFrame([features(r) for r in cc.itertuples()])
    print(f"memory pool, score >= 0.80: {len(f)} cases ({(f.outcome == 'cleared').sum()} cleared)\n")
    num = f.drop(columns=["channel"]).groupby("outcome").mean(numeric_only=True).T
    print(num.round(3).to_string())
    print("\nchannel mix:")
    print(pd.crosstab(f.channel, f.outcome, normalize="columns").round(3).to_string())


if __name__ == "__main__":
    main()

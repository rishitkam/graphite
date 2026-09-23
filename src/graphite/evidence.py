"""Turns graph query results into short evidence lines for the model.

The graph does the counting (how familiar is this region, how many other
customers used this device, how many small authorisations in the last hour)
so the model reads a handful of facts instead of hundreds of rows. Both the
GraphRAG tier and the agent's tools render through here, so the two see
evidence in exactly the same form.
"""

from collections import Counter
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np

from graphite import data, situation
from graphite import graph_tools as g

FMT = "%Y-%m-%d %H:%M:%S"
ROOT = Path(__file__).resolve().parents[2]


def _dt(s):
    return datetime.strptime(s[:19], FMT)


def _short_device(d):
    return d.split(" | ")[0][:28] if d else ""


def flagged(txn_id):
    t = g.txn_detail(txn_id)
    line = (f"FLAGGED {txn_id}: ${t['amount']:.2f} {t['channel']} product {t['product_cd']} at {t['ts']}, "
            f"region {t['addr1']}, risk score {t['risk_score']:.2f}")
    if t["device"]:
        line += f", device [{t['device']}] {t['device_seen']} for this account" + (f" via {t['proxy']}" if t["proxy"] else "")
    if t["email"]:
        line += f", email {t['email']}"
    return t, line


def baseline(t, t_end):
    p = g.card_profile(t["card_id"], t_end)
    n = p["n_txns_before"]
    if n == 0:
        return p, [f"CARD {t['card_id']}: no history before this transaction"]
    reg = p["regions"].get(t["addr1"], 0) if t["addr1"] else 0
    prod = p["products"].get(t["product_cd"], 0)
    dev = p["devices"].get(t["device"], 0) if t["device"] else None
    em = p["emails"].get(t["email"], 0) if t["email"] else None
    lines = [
        f"CARD {t['card_id']} history before this: {n} txns since {p['first_seen'][:10]}, avg ${p['avg_amount']:.2f}, max ${p['max_amount']:.2f}; "
        f"channels {p['channels']}",
        f"flagged amount is {t['amount'] / p['avg_amount']:.1f}x the card's average" if p["avg_amount"] else "",
        f"region {t['addr1']}: {reg} of {n} prior txns ({p['n_regions']} regions used; top {p['regions']})",
        f"product {t['product_cd']}: {prod} of {n} prior txns",
    ]
    if dev is not None:
        lines.append(f"this device: {dev} prior txns on the card ({p['n_devices']} devices ever)")
    if em is not None:
        lines.append(f"email {t['email']}: {em} prior txns on the card")
    return p, [x for x in lines if x]


def recent(t, t_end, hours=72, max_rows=15):
    rows = g.card_window(t["card_id"], t_end, max(1, hours // 24))
    t0 = _dt(t["ts"])
    rows = [r for r in rows if (t0 - _dt(r["ts"])).total_seconds() <= hours * 3600]
    small = [r for r in rows if r.get("channel") == "online" and float(r["amount"]) < 5
             and 0 <= (t0 - _dt(r["ts"])).total_seconds() <= 3600]
    lines = [f"LAST {hours}H ON CARD: {len(rows)} txns; {len(small)} online authorisations under $5 in the hour before the flagged txn"]
    for r in rows[-max_rows:]:
        dt = (_dt(r["ts"]) - t0).total_seconds() / 3600
        flags = " ".join(x for x in [r.get("device_seen") == "New" and "NEW-DEVICE", r.get("proxy") and "PROXY"] if x)
        lines.append(f"  {r['txn_id']} {dt:+.1f}h ${float(r['amount']):.2f} {r.get('channel', '')} {r.get('product_cd', '')} "
                     f"region {r.get('addr1', '')} {_short_device(r.get('device'))} {flags}".rstrip())
    return rows, lines


def device(t, t_end, exclude, days=30):
    if not t["device"]:
        return None, ["DEVICE: no device record (in-person or no identity data)"]
    d = g.device_neighbors(t["device"], t_end, days, exclude)
    others = [c for c in d["customers_in_window"] if not t["card_id"].startswith(c)]
    uses = d["uses_in_window"] or 1
    n_cust = d["customers_ever"]
    frauds = d["confirmed_fraud_cases_on_device"]
    lines = [
        f"DEVICE PROFILE [{t['device']}]: used by {n_cust} customers up to now. "
        f"Last {days} days: {d['uses_in_window']} uses on {d['cards_in_window']} cards ({len(others)} other customers); "
        f"marked New-to-account on {100 * d['new_device_uses_in_window'] / uses:.0f}% of those uses, "
        f"via proxy on {100 * d['proxy_uses_in_window'] / uses:.0f}%.",
    ]
    base = data.customers_per_fraud_case(t_end, exclude)
    if frauds:
        rate = f"one per {n_cust / len(frauds):.0f} of its customers"
        lines.append(f"  {len(frauds)} confirmed fraud cases were committed through this profile ({rate}"
                     + (f"; bank-wide, one confirmed fraud case per {base:.0f} active customers)" if base else ")")
                     + f": {', '.join(frauds[:8])}")
    elif base:
        lines.append(f"  no confirmed fraud cases through this profile (bank-wide, one per {base:.0f} active customers)")
    other_cards = [c for c in d["card_ids_in_window"] if c != t["card_id"]]
    if other_cards:
        lines.append(f"  other cards on it recently: {', '.join(other_cards[:12])}{' ...' if len(other_cards) > 12 else ''}")
    return d, lines


def customer(customer_id, t_end, exclude):
    o = g.customer_overview(customer_id, t_end, exclude)
    lines = [f"CUSTOMER {customer_id}: cards {o['cards']}; {len(o['prior_cases'])} prior closed cases"]
    for c in o["prior_cases"][-5:]:
        lines.append(f"  {c['case_id']} {c['card_id']} {c['outcome']} {c['pattern']} closed {c['closed_at'][:10]}")
    return o, lines


def precedent(txn_id, t_end, exclude, k=5):
    hits = g.structural_precedent(txn_id, t_end, exclude, k)
    lines = ["CLOSED CASES SHARING STRUCTURE (same device or billing region, rarer links weigh more):"]
    for h in hits:
        lines.append(f"  {h['case_id']} [{h['outcome']}, {h['pattern']}, link weight {h['weight']:.2f}]: {h['notes'][:170]}")
    return hits, lines


@lru_cache(maxsize=1)
def _scaling():
    z = np.load(ROOT / "data" / "situations.npz", allow_pickle=True)
    return {"mean": z["mean"], "std": z["std"]}


def situation_memory(txn_id, t_end, exclude, k=15):
    """How did past alerts in the most similar graph situation end?"""
    qv = situation.vector(txn_id, t_end, _scaling())
    hits = g.similar_situations(qv, t_end, exclude, k)
    if not hits:
        return hits, ["SITUATION MEMORY: no closed cases before this time"]
    w = [1 / (0.5 + (h["distance"] or 0)) for h in hits]
    share = sum(wi for wi, h in zip(w, hits) if h["outcome"] == "confirmed_fraud") / sum(w)
    n_fraud = sum(h["outcome"] == "confirmed_fraud" for h in hits)
    patterns = Counter(h["pattern"] for h in hits if h["outcome"] == "confirmed_fraud").most_common(2)
    lines = [
        f"SITUATION MEMORY: this alert's graph context is {situation.describe(txn_id, t_end)}",
        f"  of the {len(hits)} past alerts in the most similar situation, {n_fraud} were confirmed fraud and "
        f"{len(hits) - n_fraud} were cleared (similarity-weighted fraud share {share:.2f})"
        + (f"; fraud ones were mostly {', '.join(p for p, _ in patterns)}" if patterns else ""),
    ]
    for h in hits[:3]:
        lines.append(f"  nearest {h['case_id']} [{h['outcome']}, {h['pattern']}]: {h['notes'][:150]}")
    return hits, lines

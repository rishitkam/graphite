"""Proactive monitoring over the exam period: the README's optional extra.

No alert to start from. scripts/find_rings.py links customers who shared a
suspect device (New to both accounts, mostly via proxy, not a mass-market
profile) and runs TigerGraph's weakly connected components over those links.
Each component of three or more customers is a candidate ring. Here each one
becomes an analyst-style alert, investigated by the agent once per ring, not
once per card. The ring's members and devices come from the graph; the
agent judges whether it is fraud and what to do. Answer files go to
cases_proactive/ and every case is written to the graph.
"""

import json
from pathlib import Path

import pandas as pd

from graphite import alerts, assess, case_store, data, sar
from graphite.pipelines import agentic

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "cases_proactive"
WINDOW = ("2016-11-01", "2016-12-31")


def main():
    OUT.mkdir(exist_ok=True)
    rings = json.loads((ROOT / "eval" / f"rings_{WINDOW[0]}_{WINDOW[1]}.json").read_text())
    exam = {a.customer_id for a in alerts.exam_alerts()}
    tx = data._tx().reset_index().rename(columns={"index": "txn_id"})
    tx["customer"] = tx["card_id"].str.split("-").str[0]
    in_window = tx[(tx.ts >= WINDOW[0]) & (tx.ts <= f"{WINDOW[1]} 23:59:59")]
    suspect = in_window[(in_window.device_seen == "New") & in_window.proxy_type.notna()]

    for i, ring in enumerate(rings, 1):
        members = set(ring["customers"])
        if members & exam:
            continue  # already investigated as an exam case
        uses = suspect[suspect.customer.isin(members)].sort_values("ts")
        if uses.empty:
            continue
        first = uses.iloc[0]
        devices = sorted(uses.device_key.dropna().unique())
        cards = sorted(in_window[in_window.customer.isin(members)].card_id.unique())
        case_id = f"PRO-{i:03d}"
        alert = alerts.Alert(
            case_id=case_id, opened_at=str(uses.ts.max()), trigger_type="analyst_request",
            trigger_text=(f"Proactive sweep, no alert raised: {len(members)} customers are linked by {len(devices)} device "
                          f"profile(s) that were New to each account and mostly used via proxy between {WINDOW[0]} and "
                          f"{WINDOW[1]}. Review transaction {first.txn_id} on card {first.card_id} and the group behind it."),
            flagged_txn_id=first.txn_id, card_id=first.card_id, customer_id=first.customer, risk_score=None,
        )
        a, usage, trace = agentic.run(alert, alert.opened_at, set())
        if a["fraud_probability"] >= 0.5:
            a["coordinated"] = True
            a["connected_card_ids"] = [c for c in cards if c != alert.card_id]
            a["connected_device_profiles"] = sorted(set(a["connected_device_profiles"]) | set(devices))
        out = assess.answer_file(alert, a, data.amounts(), usage, steps=usage.calls + usage.tool_calls)
        out["_meta"] = {"tier": "agentic", "t_end": alert.opened_at, "calls": usage.calls, "trace": trace,
                        "card_id": alert.card_id, "customer_id": alert.customer_id,
                        "trigger_text": alert.trigger_text, "ring": {"customers": sorted(members), "devices": devices}}
        if out["sar"]["file"]:
            sar.write(out, alert, usage)
        out["tokens"], out["latency_s"] = usage.tokens, round(usage.seconds, 1)
        out["case"]["graph_case_id"] = case_store.write(out)
        out["case"]["written_to_graph"] = True
        (OUT / f"{case_id}.json").write_text(json.dumps(out, indent=2) + "\n")
        c = out["case"]
        print(f"{case_id} {len(members)} customers, {len(devices)} devices: {c['verdict']} p={c['fraud_probability']:.2f} "
              f"{c['pattern']} cards={len(c['connected_card_ids'])} sar={out['sar']['file']} tokens={out['tokens']}")


if __name__ == "__main__":
    main()

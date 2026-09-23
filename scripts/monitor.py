"""Proactive monitoring over the exam period: the README's optional extra.

The ring sweep (gsql/08_sweep.gsql) runs over November and December with no
alert to start from and no model involved. Each ring-like device it finds
becomes an analyst-style alert, investigated by the agent like any other
case: one investigation per ring, not per card, so it stays cheap. Answer
files go to cases_proactive/, and each case is written to the graph.

Thresholds (5+ customers, 80%+ New to the account, 50%+ via proxy) were set
before looking at the exam period, and on July to October they surface the
one ring the bank's own closed cases confirm.
"""

import json
from pathlib import Path

from graphite import alerts, assess, case_store, data, sar
from graphite.graph_tools import conn
from graphite.pipelines import agentic

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "cases_proactive"
WINDOW = ("2016-11-01 00:00:00", "2016-12-31 23:59:59")


def main():
    OUT.mkdir(exist_ok=True)
    rings = conn().runInstalledQuery("ring_sweep", {
        "t_start": WINDOW[0], "t_end": WINDOW[1], "min_customers": 5,
        "min_new_share": 0.8, "min_proxy_share": 0.5})[0]["rings"]
    exam_txns = {a.flagged_txn_id for a in alerts.exam_alerts()}
    dev = __import__("pandas").read_csv(ROOT / "data" / "load" / "tx_device.csv", dtype=str)
    tx = data._tx()

    for i, ring in enumerate(rings, 1):
        uses = dev[dev.device_key == ring["device"]].merge(tx[["card_id", "ts"]], left_on="txn_id", right_index=True)
        uses = uses[(uses.ts >= WINDOW[0]) & (uses.ts <= WINDOW[1]) & ~uses.txn_id.isin(exam_txns)].sort_values("ts")
        if uses.empty:
            continue
        first = uses.iloc[0]
        case_id = f"PRO-{i:03d}"
        alert = alerts.Alert(
            case_id=case_id, opened_at=str(uses.ts.max()), trigger_type="analyst_request",
            trigger_text=(f"Proactive sweep: device profile [{ring['device']}] was used by {ring['customers']} different customers "
                          f"between {ring['first_use'][:10]} and {ring['last_use'][:10]}, New to the account on "
                          f"{100 * ring['new_share']:.0f}% of {ring['uses']} uses and via proxy on {100 * ring['proxy_share']:.0f}%. "
                          f"No alert was raised on these cards. Review transaction {first.txn_id} on card {first.card_id} and the ring behind it."),
            flagged_txn_id=first.txn_id, card_id=first.card_id, customer_id=first.card_id.split("-")[0], risk_score=None,
        )
        a, usage, trace = agentic.run(alert, alert.opened_at, set())
        out = assess.answer_file(alert, a, data.amounts(), usage, steps=usage.calls + usage.tool_calls)
        out["_meta"] = {"tier": "agentic", "t_end": alert.opened_at, "calls": usage.calls, "trace": trace,
                        "card_id": alert.card_id, "customer_id": alert.customer_id, "trigger_text": alert.trigger_text,
                        "ring": ring}
        if out["sar"]["file"]:
            sar.write(out, alert, usage)
        out["tokens"], out["latency_s"] = usage.tokens, round(usage.seconds, 1)
        out["case"]["graph_case_id"] = case_store.write(out)
        out["case"]["written_to_graph"] = True
        (OUT / f"{case_id}.json").write_text(json.dumps(out, indent=2) + "\n")
        c = out["case"]
        print(f"{case_id} {ring['customers']} customers: {c['verdict']} p={c['fraud_probability']:.2f} {c['pattern']} "
              f"cards={len(c['connected_card_ids'])} exposure=${c['exposure_usd']:,.2f} sar={out['sar']['file']} tokens={out['tokens']}")


if __name__ == "__main__":
    main()

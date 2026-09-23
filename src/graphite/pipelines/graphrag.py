"""Tier 2: GraphRAG.

Tier 1's retrieved text, plus a fixed evidence pack from the graph, including
situation memory (how past alerts with the most similar graph context
ended, from TigerGraph's vector index). The
retrieval plan is set by the pipeline, not the model, and there is one model
call. Graph evidence is the only thing added over tier 1.
"""

from graphite import assess, data, evidence, llm
from graphite.pipelines import rag


def run(alert, t_end, exclude):
    usage = llm.Usage()
    rec = data.alert_record(alert.flagged_txn_id)
    hits = rag.retrieve(rag.query_text(alert, rec), t_end, exclude)

    t, flag_line = evidence.flagged(alert.flagged_txn_id)
    _, base = evidence.baseline(t, t_end)
    rows, recent = evidence.recent(t, t_end)
    dev, dev_lines = evidence.device(t, t_end, exclude)
    cust, cust_lines = evidence.customer(alert.customer_id, t_end, exclude)
    prec, prec_lines = evidence.precedent(alert.flagged_txn_id, t_end, exclude)
    mem, mem_lines = evidence.situation_memory(alert.flagged_txn_id, t_end, exclude)
    usage.tool_calls += 8

    user = "\n".join(
        [f"ALERT ({alert.trigger_type}): {alert.trigger_text}", "", "GRAPH EVIDENCE:", flag_line]
        + base + recent + mem_lines + dev_lines + cust_lines + prec_lines
        + ["", "SIMILAR PAST CASES BY TEXT:"]
        + [f"  {h['case_id']} [{h['outcome']}, {h['pattern']}]: {h['notes'][:170]}" for h in hits]
    )
    msg = llm.chat([{"role": "system", "content": assess.SYSTEM}, {"role": "user", "content": user}],
                   usage, json_mode=True)

    known = {alert.flagged_txn_id, alert.card_id, alert.customer_id}
    known |= {r["txn_id"] for r in rows} | {h["case_id"] for h in hits} | {h["case_id"] for h in prec}
    known |= {h["case_id"] for h in mem}
    known |= set(cust["cards"]) | {c["case_id"] for c in cust["prior_cases"]}
    if dev:
        known |= {t["device"]} | set(dev["confirmed_fraud_cases_on_device"]) | set(dev["customers_in_window"]) | set(dev["card_ids_in_window"])
    a = assess.link_ring_cards(assess.clean(llm.parse_json(msg.content), known), alert, dev)
    return a, usage, {"retrieved": [h["case_id"] for h in hits], "precedent": [h["case_id"] for h in prec],
                      "prompt_chars": len(user)}

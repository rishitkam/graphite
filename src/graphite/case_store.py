"""Write a finished investigation into the graph as case memory.

A FraudCase vertex with its evidence and actions, linked to the transactions,
cards, device profiles, customer and closed-case precedent it rests on. The
next investigation that touches any of those entities can find it.
"""

from datetime import datetime

from graphite.graph_tools import conn


def graph_case_id(case_id):
    return f"CASE-{case_id}"


def write(answer):
    c = conn()
    cid = graph_case_id(answer["case_id"])
    case = answer["case"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c.upsertVertex("FraudCase", cid, {
        "status": case["status"], "verdict": case["verdict"],
        "fraud_probability": case["fraud_probability"], "pattern": case["pattern"],
        "pattern_description": case["pattern_description"],
        "first_suspicious_txn_id": case["first_suspicious_txn_id"],
        "exposure_usd": case["exposure_usd"], "summary": case["summary"],
        "stop_reason": answer["stop_reason"], "written_to_graph": True,
        "created_at": now, "updated_at": now,
    })

    edges = []
    customer = answer["_meta"].get("customer_id")
    if customer:
        edges.append(("OPENED_FOR", "Customer", customer, {}))
    for t in case["affected_txn_ids"]:
        edges.append(("ABOUT_TXN", "Transaction", t, {}))
    for card in [answer["_meta"].get("card_id")] + case["connected_card_ids"]:
        if card:
            edges.append(("ABOUT_CARD", "Card", card, {}))
    for d in case["connected_device_profiles"]:
        edges.append(("LINKED_DEVICE", "DeviceProfile", d, {}))
    for p in case["similar_prior_cases"]:
        edges.append(("CITES_CASE", "ClosedCase", p, {}))
    for kind, tgt_type, tgt, attrs in edges:
        c.upsertEdge("FraudCase", cid, kind, tgt_type, tgt, attrs)

    for i, ev in enumerate(case["evidence"]):
        eid = f"{cid}-E{i + 1}"
        c.upsertVertex("Evidence", eid, {"claim": ev["claim"], "source": ev["source"], "ref": ev["ref"], "created_at": now})
        c.upsertEdge("FraudCase", cid, "HAS_EVIDENCE", "Evidence", eid)

    for phase in ("initial", "final"):
        for i, act in enumerate(answer["next_best_actions"][phase]):
            aid = f"{cid}-{phase}-{i + 1}"
            c.upsertVertex("CaseAction", aid, {"action_type": act["action"], "route": act["route"],
                                               "reason": act["reason"], "phase": phase})
            c.upsertEdge("FraudCase", cid, "RESULTED_IN", "CaseAction", aid)
    return cid

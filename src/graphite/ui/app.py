"""Demo interface: the case board, one investigation drawn as a graph, and the
three-tier scoreboard.

  .venv/bin/uvicorn graphite.ui.app:app --port 8765

Reads answer files from results/ and asks TigerGraph for each case's
neighbourhood live, so what's on screen is what's in the graph.
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from graphite import alerts, data, report
from graphite import graph_tools as g

ROOT = Path(__file__).resolve().parents[3]
app = FastAPI(title="Graphite")


def _path(tier, which, case_id):
    if which == "proactive":
        return ROOT / "cases_proactive" / f"{case_id}.json"
    return ROOT / "results" / tier / which / f"{case_id}.json"


def _load(tier, which, case_id):
    path = _path(tier, which, case_id)
    if not path.exists():
        raise HTTPException(404, f"no {tier} result for {case_id}")
    return json.loads(path.read_text())


@app.get("/")
def index():
    return FileResponse(Path(__file__).with_name("index.html"))


@app.get("/api/cases")
def cases(tier: str = "agentic", which: str = "exam"):
    if which == "proactive":
        out = []
        for p in sorted((ROOT / "cases_proactive").glob("PRO-*.json")):
            r = json.loads(p.read_text())
            c = r["case"]
            out.append({"case_id": p.stem, "trigger": "proactive sweep", "trigger_text": r["_meta"]["trigger_text"],
                        "risk_score": None, "label": None, "done": True, "verdict": c["verdict"], "status": c["status"],
                        "pattern": c["pattern"], "p0": r["_initial_probability"], "p": c["fraud_probability"],
                        "exposure": c["exposure_usd"], "sar": r["sar"]["file"], "tokens": r["tokens"]})
        return out
    source = alerts.exam_alerts() if which == "exam" else alerts.eval_alerts(("dev",) if which == "dev" else ("matched", "rare_patterns"))
    out = []
    for a in sorted(source, key=lambda x: x.case_id):
        path = _path(tier, which, a.case_id)
        row = {"case_id": a.case_id, "trigger": a.trigger_type, "trigger_text": a.trigger_text,
               "risk_score": a.risk_score, "label": a.label, "done": path.exists()}
        if path.exists():
            r = json.loads(path.read_text())
            c = r["case"]
            row.update({"verdict": c["verdict"], "status": c["status"], "pattern": c["pattern"],
                        "p0": r["_initial_probability"], "p": c["fraud_probability"],
                        "exposure": c["exposure_usd"], "sar": r["sar"]["file"], "tokens": r["tokens"]})
        out.append(row)
    return out


@app.get("/api/case/{tier}/{which}/{case_id}")
def case(tier: str, which: str, case_id: str):
    return _load(tier, which, case_id)


@app.get("/api/graph/{tier}/{which}/{case_id}")
def graph(tier: str, which: str, case_id: str):
    """The investigation's neighbourhood, weighted by how much each part mattered."""
    r = _load(tier, which, case_id)
    c = r["case"]
    meta = r["_meta"]
    flagged = r["case"]["first_suspicious_txn_id"] or next(
        (a.flagged_txn_id for a in (alerts.exam_alerts() + alerts.eval_alerts(("matched", "rare_patterns", "dev")))
         if a.case_id == case_id), None)
    t = g.txn_detail(flagged)
    nodes, edges = {}, []

    def node(nid, kind, label, weight=0.3, **extra):
        nodes[nid] = {"id": nid, "kind": kind, "label": label, "weight": max(weight, nodes.get(nid, {}).get("weight", 0)), **extra}

    def edge(a, b, label, weight=0.3):
        edges.append({"source": a, "target": b, "label": label, "weight": weight})

    affected = set(c["affected_txn_ids"])
    card = meta.get("card_id") or t["card_id"]
    customer = meta.get("customer_id") or card.split("-")[0]
    node(customer, "customer", customer, 0.6)
    node(card, "card", card, 0.9)
    edge(customer, card, "owns", 0.6)
    node(flagged, "txn", f"${t['amount']:.0f}", 1.0, flagged=True, detail=f"{t['channel']} {t['product_cd']} {t['ts']}")
    edge(card, flagged, "made", 1.0)
    for tid in list(affected - {flagged})[:10]:
        rec = data.alert_record(tid)
        node(tid, "txn", f"${rec['amount']:.0f}", 0.8, detail=f"{rec['channel']} {rec['ts']}")
        edge(card, tid, "made", 0.8)

    ring = c["connected_card_ids"]
    ring_devices = meta.get("ring", {}).get("devices", [])
    if ring_devices:
        # A proactive ring: every member card, linked through each suspect device.
        for d in ring_devices:
            node(d, "device", d.split(" | ")[0], 1.0, detail=d)
        edge(flagged, ring_devices[0], "from device", 1.0)
        member_devices = data._tx()[data._tx()["card_id"].isin(ring + [card])]
        for other in ring[:24]:
            node(other, "card", other, 0.75, ring=True)
            used = member_devices[(member_devices.card_id == other) & member_devices.device_key.isin(ring_devices)].device_key.unique()
            for d in (used if len(used) else ring_devices[:1]):
                edge(other, d, "suspect device", 0.75)
        if len(ring) > 24:
            node("more-ring", "more", f"+{len(ring) - 24} more cards", 0.5)
            edge("more-ring", ring_devices[0], "", 0.5)
    elif t["device"]:
        dev_weight = 1.0 if (c["connected_device_profiles"] or ring) else 0.4
        label = t["device"].split(" | ")[0]
        node(t["device"], "device", label, dev_weight, detail=t["device"], seen=t["device_seen"], proxy=t["proxy"])
        edge(flagged, t["device"], f"from device ({t['device_seen'] or '?'})" + (" via proxy" if t["proxy"] else ""), dev_weight)
        for other in ring[:14]:
            node(other, "card", other, 0.75, ring=True)
            edge(other, t["device"], "same device", 0.75)
        if len(ring) > 14:
            node("more-ring", "more", f"+{len(ring) - 14} more cards", 0.5)
            edge("more-ring", t["device"], "", 0.5)

    closed = data.closed_cases().set_index("case_id")
    for pid in c["similar_prior_cases"][:6]:
        if pid in closed.index:
            row = closed.loc[pid]
            node(pid, "closed", pid, 0.55, outcome=row.outcome, pattern=row.pattern, detail=row.analyst_notes[:220])
            edge(flagged, pid, "precedent", 0.55)

    return {"nodes": list(nodes.values()), "edges": edges, "flagged": flagged}


@app.get("/api/preview/{case_id}")
def preview(case_id: str):
    """Graph evidence for an exam case before any model has looked at it.

    Pure graph and vector queries, no model tokens: what the investigator
    would start from.
    """
    from graphite import evidence
    a = next((x for x in alerts.exam_alerts() if x.case_id == case_id), None)
    if a is None:
        raise HTTPException(404, case_id)
    t, flag_line = evidence.flagged(a.flagged_txn_id)
    lines = [flag_line] + evidence.baseline(t, a.opened_at)[1]
    if a.trigger_type == "customer_report":
        lines += evidence.recurring(a.flagged_txn_id, a.opened_at)[1]
    lines += evidence.situation_memory(a.flagged_txn_id, a.opened_at, set())[1][:3]
    lines += evidence.device(t, a.opened_at, set())[1]
    return {"case_id": case_id, "trigger": a.trigger_type, "trigger_text": a.trigger_text, "lines": lines}


@app.get("/api/compare")
def compare(which: str = "dev"):
    return {t: report.summarise(report.load(t, which)) for t in report.TIERS}

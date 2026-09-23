"""Thin wrappers over the installed GSQL queries.

Each returns a compact dict, not raw TigerGraph JSON: the model only ever sees
what these functions return, so keeping them small is where most of the token
budget gets saved.
"""

import os
from collections import Counter

from graphite import mcp_client
from graphite.tg import connect

_conn = None
NONE = "__none__"  # an empty SET<STRING> arrives as NULL, so always send one value


def conn():
    global _conn
    if _conn is None:
        _conn = connect()
    return _conn


# Graph queries go through the official TigerGraph MCP server by default.
# GRAPHITE_TRANSPORT=direct uses pyTigerGraph instead (same queries, same
# results), which is only there for debugging the MCP path.
TRANSPORT = os.getenv("GRAPHITE_TRANSPORT", "mcp")


def _run(query, params):
    if TRANSPORT == "mcp":
        return mcp_client.run_installed_query(query, params)
    fixed = {k: (v,) if k in ("t", "c", "d", "u") else v for k, v in params.items()}
    return conn().runInstalledQuery(query, fixed)


def _excl(exclude):
    return sorted(exclude) or [NONE]


def txn_detail(txn_id):
    out = _run("txn_detail", {"t": txn_id})
    attrs = {k.split(".", 1)[1]: v for k, v in out[0]["txn"][0]["attributes"].items()}
    links = out[1]
    return {
        "txn_id": txn_id,
        **attrs,
        "card_id": links["card"][0] if links["card"] else None,
        "email": links["email"][0] if links["email"] else None,
        "device": links["device"][0] if links["device"] else None,
        "device_seen": links["device_seen"][0] if links["device_seen"] else None,
        "proxy": (links["proxy"][0] or None) if links["proxy"] else None,
    }


def card_window(card_id, t_end, days):
    out = _run("card_window", {"c": card_id, "t_end": t_end, "days": days})
    rows = []
    for v in out[0]["txns"]:
        a = {k.split(".", 1)[1].lstrip("@"): val for k, val in v["attributes"].items()}
        rows.append({"txn_id": v["v_id"], **{k: val for k, val in a.items() if val not in ("", None)}})
    return sorted(rows, key=lambda r: r["ts"])


def card_profile(card_id, t_end):
    p = _run("card_profile", {"c": card_id, "t_end": t_end})[0]

    def top(m, n=5):
        return dict(Counter(m).most_common(n))

    return {
        "n_txns_before": p["n_txns"],
        "avg_amount": round(p["avg_amount"], 2),
        "max_amount": p["max_amount"],
        "first_seen": p["first_seen"],
        "regions": top(p["regions"]),
        "n_regions": len(p["regions"]),
        "products": top(p["products"]),
        "channels": p["channels"],
        "emails": top(p["emails"], 3),
        "devices": top(p["devices"], 3),
        "n_devices": len(p["devices"]),
    }


def device_neighbors(device_key, t_end, days=30, exclude=()):
    out = _run("device_neighbors", {"d": device_key, "t_end": t_end, "days": days, "exclude": _excl(exclude)})
    r = {}
    for part in out:
        r.update(part)
    return {
        "device": device_key,
        "uses_in_window": r["uses_window"],
        "new_device_uses_in_window": r["new_uses_window"],
        "proxy_uses_in_window": r["proxy_uses_window"],
        "cards_in_window": len(r["card_uses_window"]),
        "card_ids_in_window": sorted(r["card_uses_window"]),
        "customers_in_window": sorted(r["customers_window"]),
        "customers_ever": r["customers_ever"],
        "confirmed_fraud_cases_on_device": sorted(r["fraud_cases_on_device"]),
    }


def customer_overview(customer_id, t_end, exclude=()):
    out = _run("customer_overview", {"u": customer_id, "t_end": t_end, "exclude": _excl(exclude)})
    r = {}
    for part in out:
        r.update(part)
    cases = sorted(r["prior_cases"], key=lambda c: c["closed_at"])
    return {
        "cards": r["cards"],
        "prior_cases": [
            {"case_id": c["case_id"], "card_id": c["card_id"], "outcome": c["outcome"],
             "pattern": c["pattern"], "closed_at": c["closed_at"]}
            for c in cases
        ],
    }


def structural_precedent(txn_id, t_end, exclude=(), k=5):
    out = _run("structural_precedent", {"t": txn_id, "t_end": t_end, "exclude": _excl(exclude), "k": k})
    return [
        {"case_id": h["case_id"], "outcome": h["outcome"], "pattern": h["pattern"],
         "weight": round(h["weight"], 3), "notes": h["notes"]}
        for h in out[0]["precedent"]
    ]


def _vector_query(name, qv, t_end, exclude, k):
    params = {"qv": [float(x) for x in qv], "t_end": t_end, "exclude": _excl(exclude), "k": k}
    out = mcp_client.run_installed_query(name, params) if TRANSPORT == "mcp" else conn().runInstalledQuery(name, params, usePost=True)
    dist = {}
    for part in out:
        if "dist" in part:
            dist = part["dist"]
    hits = []
    for v in out[0]["hits"]:
        a = {key.split(".", 1)[1]: val for key, val in v["attributes"].items()}
        hits.append({"case_id": a["case_id"], "outcome": a["outcome"], "pattern": a["pattern"],
                     "notes": a["analyst_notes"], "distance": dist.get(v["v_id"])})
    return sorted(hits, key=lambda h: (h["distance"] is None, h["distance"]))


def similar_notes(qv, t_end, exclude=(), k=5):
    return _vector_query("similar_notes", qv, t_end, exclude, k)


def similar_situations(qv, t_end, exclude=(), k=15):
    return _vector_query("similar_situations", qv, t_end, exclude, k)


def search_policy(qv, k=3):
    params = {"qv": [float(x) for x in qv], "k": k}
    out = mcp_client.run_installed_query("search_policy", params) if TRANSPORT == "mcp" else conn().runInstalledQuery("search_policy", params, usePost=True)
    return [{key.split(".", 1)[1]: val for key, val in v["attributes"].items()} for v in out[0]["hits"]]

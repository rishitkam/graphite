"""Tier 1: plain RAG.

Retrieve the closed-case narratives most similar to the alert from
TigerGraph's vector index, one model call. No graph traversal: the model
sees the alert, the flagged transaction's own record, and the retrieved text. Memory is limited to
cases closed before the investigation time and never includes the case
being evaluated.
"""

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

from graphite import assess, data, llm
from graphite import graph_tools as g

K = 5
CACHE = Path(__file__).resolve().parents[3] / "data" / "case_embeddings.npy"


@lru_cache(maxsize=1)
def _model():
    return TextEmbedding("BAAI/bge-small-en-v1.5")


@lru_cache(maxsize=1)
def _index():
    cc = data.closed_cases()
    if CACHE.exists():
        vecs = np.load(CACHE)
    else:
        vecs = np.array(list(_model().embed(cc["analyst_notes"].tolist())), dtype=np.float32)
        np.save(CACHE, vecs)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    return cc, vecs


def query_text(alert, rec):
    parts = [alert.trigger_text,
             f"{rec.get('channel', '')} purchase of ${rec['amount']:.2f}, product {rec.get('product_cd', '')}"]
    if rec.get("device"):
        parts.append(f"device {rec['device']} marked {rec.get('device_seen', 'unknown')}"
                     + (f" behind {rec['proxy']}" if rec.get("proxy") else ""))
    if rec.get("billing_region"):
        parts.append(f"billing region {rec['billing_region']}")
    return ". ".join(parts)


def embed(text):
    return np.array(next(_model().embed([text])), dtype=np.float32)


def retrieve(text, t_end, exclude, k=K):
    """Closed cases whose narratives read most like the query, from TigerGraph's vector index."""
    return g.similar_notes(embed(text), t_end, exclude, k)


def run(alert, t_end, exclude):
    usage = llm.Usage()
    rec = data.alert_record(alert.flagged_txn_id)
    hits = retrieve(query_text(alert, rec), t_end, exclude)
    usage.tool_calls += 1

    user = (
        f"ALERT ({alert.trigger_type}): {alert.trigger_text}\n"
        f"FLAGGED TRANSACTION RECORD: {json.dumps(rec)}\n\n"
        f"SIMILAR PAST CASES (retrieved by text similarity):\n"
        + "\n".join(f"- {h['case_id']} [{h['outcome']}, {h['pattern']}]: {h['notes']}" for h in hits)
    )
    msg = llm.chat([{"role": "system", "content": assess.SYSTEM}, {"role": "user", "content": user}],
                   usage, json_mode=True)
    known = [alert.flagged_txn_id, alert.card_id, alert.customer_id, rec.get("device", "")] + [h["case_id"] for h in hits]
    a = assess.link_ring_cards(assess.clean(llm.parse_json(msg.content), known), alert, None)
    return a, usage, {"retrieved": [h["case_id"] for h in hits]}

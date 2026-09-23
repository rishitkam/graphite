"""Compare the three tiers on a set.

  python -m graphite.report --set dev
  python -m graphite.report --set eval --markdown eval/RESULTS.md

Accuracy, AUC and calibration are measured on each tier's initial fraud
probability: the assessment made from evidence alone, before any simulated
customer reply. The simulated reply follows the investigator's own estimate,
so scoring after it would reward confidence, not evidence.
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TIERS = ["rag", "graphrag", "agentic"]
NAMES = {"rag": "RAG", "graphrag": "GraphRAG", "agentic": "Agentic GraphRAG",
         "memory": "Graph memory only (no LLM)"}


def auc(pos, neg):
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def load(tier, which):
    d = ROOT / "results" / tier / which
    return [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))] if d.exists() else []


def summarise(rows, slice_name=None):
    rows = [r for r in rows if slice_name is None or r["_meta"].get("eval_slice") == slice_name]
    labelled = [r for r in rows if r["_meta"].get("label")]
    out = {"n": len(rows)}
    if labelled:
        p = [r["_initial_probability"] for r in labelled]
        y = [r["_meta"]["label"] == "fraud" for r in labelled]
        out["accuracy"] = sum((pi >= 0.5) == yi for pi, yi in zip(p, y)) / len(y)
        out["auc"] = auc([pi for pi, yi in zip(p, y) if yi], [pi for pi, yi in zip(p, y) if not yi])
        out["brier"] = sum((pi - yi) ** 2 for pi, yi in zip(p, y)) / len(y)
        fraud = [r for r in labelled if r["_meta"]["label"] == "fraud"]
        out["fraud_recall"] = sum(r["_initial_probability"] >= 0.5 for r in fraud) / len(fraud) if fraud else None
        legit = [r for r in labelled if r["_meta"]["label"] == "legitimate"]
        out["legit_specificity"] = sum(r["_initial_probability"] < 0.5 for r in legit) / len(legit) if legit else None
        out["pattern_accuracy"] = (sum(r["case"]["pattern"] == r["_meta"]["label_pattern"] for r in fraud) / len(fraud)) if fraud else None
    if rows:
        out["tokens"] = sum(r["tokens"] for r in rows) / len(rows)
        out["llm_calls"] = sum(r["_meta"]["calls"] for r in rows) / len(rows)
        out["tool_calls"] = sum(r["tool_calls"] for r in rows) / len(rows)
        out["latency_s"] = sum(r["latency_s"] for r in rows) / len(rows)
    return out


def memory_only(which, case_ids):
    """Reference row with no language model: predict the similarity-weighted
    fraud share of the 15 most similar past situations, from TigerGraph's
    vector index, under the same time and exclusion rules as the tiers."""
    from graphite import alerts, data, evidence, run
    wanted = {"dev": ("dev",), "eval": ("matched", "rare_patterns")}[which]
    rows = []
    for a in alerts.eval_alerts(wanted):
        if case_ids and a.case_id not in case_ids:
            continue
        t_end = run.investigation_time(a, which)
        hits, _ = evidence.situation_memory(a.flagged_txn_id, t_end, alerts.holdout_ids())
        share = evidence.adjusted(evidence.memory_share(hits), data.memory_fraud_share(t_end, alerts.holdout_ids()))
        rows.append({"_initial_probability": share, "_meta": {"label": a.label, "label_pattern": a.label_pattern,
                     "eval_slice": a.eval_slice, "calls": 0}, "case": {"pattern": "none"}, "tokens": 0,
                     "tool_calls": 1, "latency_s": 0})
    return rows


def fmt(v, pct=False):
    if v is None:
        return "n/a"
    return f"{100 * v:.1f}%" if pct else (f"{v:.3f}" if isinstance(v, float) and v < 10 else f"{v:,.0f}" if isinstance(v, float) else str(v))


def table(which, slice_name=None, with_memory=True):
    stats = {t: summarise(load(t, which), slice_name) for t in TIERS}
    cols = list(TIERS)
    if with_memory and which in ("dev", "eval"):
        ids = {json.loads(p.read_text())["case_id"] for t in TIERS for p in (ROOT / "results" / t / which).glob("*.json")}
        stats["memory"] = summarise(memory_only(which, ids), slice_name)
        cols = ["memory"] + cols
    rows = [("cases", "n", False), ("accuracy", "accuracy", True), ("AUC", "auc", False),
            ("Brier (lower is better)", "brier", False), ("fraud recall", "fraud_recall", True),
            ("legit specificity", "legit_specificity", True), ("pattern accuracy (fraud)", "pattern_accuracy", True),
            ("tokens / case", "tokens", False), ("LLM calls / case", "llm_calls", False),
            ("graph+retrieval calls / case", "tool_calls", False), ("seconds / case", "latency_s", False)]
    lines = ["| metric | " + " | ".join(NAMES[t] for t in cols) + " |", "|---|" + "---|" * len(cols)]
    for label, key, pct in rows:
        lines.append(f"| {label} | " + " | ".join(fmt(stats[t].get(key), pct) for t in cols) + " |")
    return "\n".join(lines), stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", dest="which", default="dev")
    ap.add_argument("--slice", default=None)
    ap.add_argument("--markdown", default=None)
    args = ap.parse_args()
    md, stats = table(args.which, args.slice)
    print(md)
    base = stats["rag"].get("accuracy")
    if base:
        for t in TIERS[1:]:
            acc = stats[t].get("accuracy")
            if acc is not None:
                print(f"{NAMES[t]} vs RAG accuracy: {100 * (acc - base):+.1f} points ({100 * (acc - base) / base:+.0f}% relative)")
    if args.markdown:
        Path(args.markdown).write_text(md + "\n")


if __name__ == "__main__":
    main()

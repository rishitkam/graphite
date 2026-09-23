"""Run a tier over the eval set or the 20 exam cases.

  python -m graphite.run --tier rag --set eval [--limit 20]
  python -m graphite.run --tier graphrag --set exam

Every case is cached under results/<tier>/<set>/, so a run that hits the
daily rate limit resumes where it stopped.

--set dev is for iterating on the pipelines. --set eval is the held-out
test set, run once at the end. Dev and eval cases are investigated six hours
after their flagged transaction (see EVAL_WINDOW); exam cases as of their
real opened_at. Every held-out case is excluded from memory in dev and eval.
"""

import argparse
import importlib
import json
import random
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from graphite import alerts, assess, case_store, data, sar

ROOT = Path(__file__).resolve().parents[2]


# Every exam case is opened 1 to 6 hours after its flagged transaction. In the
# closed history, false alarms were opened within hours and fraud a median of
# 22 hours later, so using each closed case's real opened_at would leak the
# label. Instead every eval case is investigated 6 hours after its flagged
# transaction: the same for both classes, and the same window the exam has.
EVAL_WINDOW = timedelta(hours=6)


def investigation_time(alert, which):
    if which == "exam":
        return alert.opened_at
    ts = datetime.strptime(data.alert_record(alert.flagged_txn_id)["ts"], "%Y-%m-%d %H:%M:%S")
    return (ts + EVAL_WINDOW).strftime("%Y-%m-%d %H:%M:%S")


def run_case(tier, alert, which):
    module = importlib.import_module(f"graphite.pipelines.{tier}")
    t_end = investigation_time(alert, which)
    exclude = alerts.holdout_ids() if which in ("dev", "eval") else set()
    a, usage, trace = module.run(alert, t_end, exclude)
    out = assess.answer_file(alert, a, data.amounts(), usage, steps=usage.calls + usage.tool_calls)
    if which == "exam" and out["sar"]["file"]:
        sar.write(out, alert, usage)
        out["tokens"], out["latency_s"] = usage.tokens, round(usage.seconds, 1)
    out["_meta"] = {"tier": tier, "t_end": t_end, "label": alert.label, "label_pattern": alert.label_pattern,
                    "eval_slice": alert.eval_slice, "calls": usage.calls, "trace": trace,
                    "card_id": alert.card_id, "customer_id": alert.customer_id}
    # Only the real submission writes case memory; dev and eval runs must not
    # leave cases behind for later runs to retrieve.
    if which == "exam" and tier == "agentic":
        out["case"]["graph_case_id"] = case_store.write(out)
        out["case"]["written_to_graph"] = True
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", required=True, choices=["rag", "graphrag", "agentic"])
    ap.add_argument("--set", dest="which", default="eval", choices=["dev", "eval", "exam"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", nargs="*", default=[])
    args = ap.parse_args()

    items = {"dev": lambda: alerts.eval_alerts(("dev",)), "eval": alerts.eval_alerts,
             "exam": alerts.exam_alerts}[args.which]()
    items = sorted(items, key=lambda a: a.case_id)
    if args.only:
        items = [a for a in items if a.case_id in args.only]
    if args.limit:
        # Case ids run in date order, so the first N are all early July with
        # almost no card history. Shuffle with a fixed seed, then interleave
        # classes, so a small debug run looks like the whole set.
        rng = random.Random(7)
        rng.shuffle(items)
        fraud = [a for a in items if a.label != "legitimate"]
        legit = [a for a in items if a.label == "legitimate"]
        mixed = [x for pair in zip(fraud, legit) for x in pair] + fraud[len(legit):] + legit[len(fraud):]
        items = mixed[:args.limit]

    out_dir = ROOT / "results" / args.tier / args.which
    out_dir.mkdir(parents=True, exist_ok=True)
    done = failed = 0
    for alert in items:
        path = out_dir / f"{alert.case_id}.json"
        if path.exists():
            continue
        try:
            result = run_case(args.tier, alert, args.which)
        except Exception as e:
            if "per day" in str(e).lower():
                print("daily rate limit hit, stopping; rerun later to resume", file=sys.stderr)
                break
            failed += 1
            print(f"{alert.case_id} FAILED: {e}", file=sys.stderr)
            traceback.print_exc(limit=2)
            continue
        path.write_text(json.dumps(result, indent=2))
        done += 1
        c = result["case"]
        print(f"{alert.case_id:<9} p0={result['_initial_probability']:.2f} p={c['fraud_probability']:.2f} "
              f"{c['verdict']:<10} {c['pattern']:<28} label={alert.label or '-':<10} "
              f"tok={result['tokens']:<5} calls={result['_meta']['calls']}", flush=True)
    print(f"{done} new, {failed} failed, results in {out_dir.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

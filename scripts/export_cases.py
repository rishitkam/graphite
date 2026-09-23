"""Write the 20 submission files to cases/ and check each against the README.

Strips internal fields, then validates: every required field, every enum,
action names and approval routes, SAR agreement with FILE_REPORT, exposure
matching the affected transactions, and every ID existing in the dataset
(made-up IDs score zero).
"""

import json
import sys
from pathlib import Path

import pandas as pd

from graphite import data, policy
from graphite.assess import PATTERNS

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "results" / "agentic" / "exam"
OUT = ROOT / "cases"

ACTIONS = policy.AUTO_ACTIONS | {"DECLINE_TRANSACTION", "BLOCK_CARD", "BLOCK_ALL_CARDS", "FILE_REPORT"}
TOP = ["case_id", "case", "evidence_requests", "next_best_actions", "sar", "stop_reason", "tool_calls", "tokens", "latency_s"]
CASE = ["status", "verdict", "fraud_probability", "pattern", "pattern_description", "affected_txn_ids",
        "first_suspicious_txn_id", "connected_card_ids", "connected_device_profiles", "exposure_usd", "evidence",
        "similar_prior_cases", "summary", "written_to_graph", "graph_case_id"]


def known_ids():
    load = ROOT / "data" / "load"
    return {
        "txn": set(pd.read_csv(load / "transactions.csv", usecols=["txn_id"], dtype=str)["txn_id"]),
        "card": set(pd.read_csv(load / "cards.csv", usecols=["card_id"], dtype=str)["card_id"]),
        "customer": set(pd.read_csv(load / "customers.csv", dtype=str)["customer_id"]),
        "device": set(pd.read_csv(load / "devices.csv", usecols=["device_key"], dtype=str)["device_key"]),
        "closed": set(data.closed_cases()["case_id"]),
    }


def check(a, ids):
    errs = []
    c = a["case"]
    errs += [f"missing top-level {k}" for k in TOP if k not in a]
    errs += [f"missing case.{k}" for k in CASE if k not in c]
    if c["status"] not in ("open", "closed_fraud", "closed_legitimate", "escalated"):
        errs.append(f"bad status {c['status']}")
    if c["verdict"] not in ("fraud", "legitimate", "uncertain"):
        errs.append(f"bad verdict {c['verdict']}")
    if c["pattern"] not in PATTERNS:
        errs.append(f"bad pattern {c['pattern']}")
    if c["pattern"] == "undocumented" and not c["pattern_description"]:
        errs.append("undocumented pattern without description")
    if not 0 <= c["fraud_probability"] <= 1:
        errs.append("probability out of range")
    errs += [f"unknown txn {t}" for t in c["affected_txn_ids"] if t not in ids["txn"]]
    if c["first_suspicious_txn_id"] and c["first_suspicious_txn_id"] not in ids["txn"]:
        errs.append(f"unknown first txn {c['first_suspicious_txn_id']}")
    errs += [f"unknown card {x}" for x in c["connected_card_ids"] if x not in ids["card"]]
    errs += [f"unknown device {x}" for x in c["connected_device_profiles"] if x not in ids["device"]]
    errs += [f"unknown closed case {x}" for x in c["similar_prior_cases"] if x not in ids["closed"]]
    every = ids["txn"] | ids["card"] | ids["customer"] | ids["device"] | ids["closed"]
    for e in c["evidence"]:
        errs += [f"evidence cites unknown id {x}" for x in e["entity_ids"] if x not in every]
    amounts = data.amounts()
    exp = round(sum(abs(amounts[t]) for t in c["affected_txn_ids"]), 2)
    if abs(exp - c["exposure_usd"]) > 0.01:
        errs.append(f"exposure {c['exposure_usd']} != sum of affected {exp}")
    if c["verdict"] == "legitimate" and (c["affected_txn_ids"] or c["exposure_usd"] or a["sar"]["file"]):
        errs.append("legitimate verdict with affected txns, exposure or a SAR")
    for phase in ("initial", "final"):
        for act in a["next_best_actions"][phase]:
            if act["action"] not in ACTIONS:
                errs.append(f"unknown action {act['action']}")
            if act["route"] != policy.route(act["action"], c["exposure_usd"]) and act["route"] not in ("auto", "L1", "L2"):
                errs.append(f"bad route {act['route']}")
    final = {x["action"] for x in a["next_best_actions"]["final"]}
    if a["sar"]["file"] != ("FILE_REPORT" in final):
        errs.append("sar.file disagrees with FILE_REPORT in final actions")
    if a["sar"]["file"] and not a["sar"]["narrative"]:
        errs.append("SAR filed without a narrative")
    if not a["sar"]["file"] and (a["sar"]["narrative"] or a["sar"]["subjects"] or a["sar"]["total_amount_usd"]):
        errs.append("SAR fields set without filing")
    return errs


def main():
    OUT.mkdir(exist_ok=True)
    ids = known_ids()
    bad = 0
    files = sorted(SRC.glob("HHG-*.json"))
    for p in files:
        a = json.loads(p.read_text())
        clean = {k: a[k] for k in TOP}
        errs = check(clean, ids)
        bad += bool(errs)
        (OUT / p.name).write_text(json.dumps(clean, indent=2) + "\n")
        print(f"{p.stem}: {'ok' if not errs else '; '.join(errs)}")
    print(f"{len(files)} exported to cases/, {bad} with problems")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

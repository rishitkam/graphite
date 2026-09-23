"""Shared by all three tiers: the system prompt, the assessment format, the
simulated evidence step, and assembly of the final answer file.

The prompt carries only what the dataset README states (patterns, policy).
Nothing learned from exploring the data goes in here, or every tier would
get it for free and the comparison would stop measuring whether a tier can
find it in the evidence.
"""

from graphite import policy
from graphite.policy import Assessment, Reply

PATTERNS = [
    "card_testing", "card_not_present_fraud", "card_not_present_new_device",
    "out_of_region_use", "account_takeover", "undocumented", "none",
]

SYSTEM = """You are a bank fraud investigator. You assess one alert using only the evidence you are given, and you answer in JSON.

Known fraud patterns (the bank's analysts recognize these five; others exist in the data):
1. card_testing: three or more tiny online authorizations, often under $5, then a larger purchase.
2. card_not_present_fraud: number used online without the card. Amounts or products that don't fit the cardholder's history, often 2 to 4 within 48 hours. One unusual online purchase alone is ambiguous.
3. card_not_present_new_device: as above, with the device marked New for this account, sometimes behind a proxy. Stronger than 2, still not proof: people buy new phones.
4. out_of_region_use: card-present purchases in a billing region the cardholder has no history in, while normal activity continues at home. Several days in one new region is a trip, not a clone.
5. account_takeover: mixed-channel activity inconsistent with the cardholder, often with device and match anomalies.
Use "undocumented" when evidence shows coordinated or repeated abuse that fits none of these (describe it). Use "none" if legitimate.
Abuse coordinated across several different customers (the same device profile, region or recipient used for fraud on many cards) is not one of the five single-cardholder patterns: call it undocumented, set coordinated and shared_origin, and list the linked cards and device profiles.

Rules of evidence:
- The model risk score is an input, often wrong in both directions. Never treat it as the answer.
- About half of alerts are legitimate. Blocking everything is wrong.
- fraud_probability must be calibrated: say 0.5 when the evidence is genuinely balanced.
- Only cite IDs that appear in the evidence you were given. Never invent an ID.
- Count only independent evidence: two facts from the same observation are one.

Return exactly this JSON:
{
  "fraud_probability": number 0-1,
  "pattern": one of %s,
  "pattern_description": "2-3 sentences if undocumented, else empty",
  "evidence": [{"claim": str, "source": "graph"|"document", "ref": str, "entity_ids": [str]}],
  "affected_txn_ids": [str],
  "first_suspicious_txn_id": str,
  "connected_card_ids": [str],
  "connected_device_profiles": [str],
  "shared_origin": "the shared device/region/email if several cards show fraud from it, else empty",
  "card_testing": bool,
  "large_purchase_cleared": bool,
  "recurring_match": bool,
  "coordinated": bool,
  "evidence_conflicts": bool,
  "similar_prior_cases": [closed case ids you actually used],
  "summary": "2-4 sentences"
}""" % PATTERNS


# For tiers that have case memory. Ordinary base-rate reasoning, not anything
# learned from this data: memory says how alerts like this one actually
# ended, and specific evidence should move you off that, not replace it.
MEMORY_GUIDE = """How to weigh the evidence:
- SITUATION MEMORY is the base rate: how past alerts in the most similar graph situation actually ended. Anchor fraud_probability on its fraud share.
- Move away from it only for specific evidence the memory cannot see: a device or region shared across other customers' fraud, card testing, a customer's own recurring pattern, or a conflicting precedent that shares the exact device.
- Looking ordinary is not, by itself, evidence of legitimacy, and looking unusual is not, by itself, evidence of fraud: let the base rate speak unless specific evidence says otherwise. Say which evidence moved you, and by how much."""


def clean(raw, known_ids):
    """Normalise the model's JSON and drop any ID it wasn't shown."""
    known = set(known_ids)

    def ids(xs):
        return [str(x) for x in (xs or []) if str(x) in known]

    def card_ids(xs):
        # A customer id (C01289) where a card id (C01289-K1) belongs scores zero.
        return [x for x in ids(xs) if "-K" in x]

    p = float(raw.get("fraud_probability", 0.5))
    pattern = raw.get("pattern") if raw.get("pattern") in PATTERNS else "none"
    evidence = [
        {"claim": str(e.get("claim", ""))[:400], "source": e.get("source") if e.get("source") in ("graph", "document") else "graph",
         "ref": str(e.get("ref", ""))[:120], "entity_ids": ids(e.get("entity_ids"))}
        for e in (raw.get("evidence") or [])[:8] if e.get("claim")
    ]
    return {
        "fraud_probability": min(max(p, 0.0), 1.0),
        "pattern": pattern,
        "pattern_description": str(raw.get("pattern_description") or "") if pattern == "undocumented" else "",
        "evidence": evidence,
        "affected_txn_ids": ids(raw.get("affected_txn_ids")),
        "first_suspicious_txn_id": raw.get("first_suspicious_txn_id") if str(raw.get("first_suspicious_txn_id")) in known else "",
        "connected_card_ids": card_ids(raw.get("connected_card_ids")),
        "connected_device_profiles": [d for d in (raw.get("connected_device_profiles") or []) if d in known],
        "shared_origin": str(raw.get("shared_origin") or ""),
        "card_testing": bool(raw.get("card_testing")),
        "large_purchase_cleared": bool(raw.get("large_purchase_cleared")),
        "recurring_match": bool(raw.get("recurring_match")),
        "coordinated": bool(raw.get("coordinated")),
        "evidence_conflicts": bool(raw.get("evidence_conflicts")),
        "similar_prior_cases": [c for c in (raw.get("similar_prior_cases") or []) if c in known],
        "summary": str(raw.get("summary") or ""),
    }


def link_ring_cards(a, alert, device_result):
    """If the model concluded coordinated abuse through a device, the connected
    cards are the other cards that used that device in the window. That's a
    fact from the graph, so it's filled in rather than left to the model."""
    if device_result and (a["coordinated"] or a["pattern"] == "undocumented"):
        others = set(device_result["card_ids_in_window"]) - {alert.card_id}
        a["connected_card_ids"] = sorted((set(a["connected_card_ids"]) | others) - {alert.card_id})
        if device_result["device"] not in a["connected_device_profiles"]:
            a["connected_device_profiles"].append(device_result["device"])
    else:
        a["connected_card_ids"] = [c for c in a["connected_card_ids"] if c != alert.card_id]
    return a


def to_policy(a, alert, amounts, reply=Reply.NONE):
    affected = a["affected_txn_ids"] or ([alert.flagged_txn_id] if a["fraud_probability"] >= 0.5 else [])
    exposure = round(sum(abs(amounts.get(t, 0.0)) for t in affected), 2)
    return Assessment(
        fraud_probability=a["fraud_probability"],
        exposure_usd=exposure,
        independent_evidence=len({e["ref"] for e in a["evidence"]}),
        pattern=a["pattern"],
        customer_disputed=alert.trigger_type == "customer_report",
        reply=reply,
        recurring_match=a["recurring_match"],
        shared_origin=a["shared_origin"],
        connected_cards=a["connected_card_ids"],
        card_testing=a["card_testing"],
        large_purchase_cleared=a["large_purchase_cleared"],
        coordinated=a["coordinated"],
        evidence_conflicts=a["evidence_conflicts"],
    )


# Customer replies aren't in the dataset; the README says to simulate them and
# state the assumption. The simulated reply follows the investigator's own
# assessment (it can't see the truth), and a reply moves the odds 4x.
REPLY_ODDS = 4.0


def simulate_reply(p, alert):
    denied = p >= 0.5
    if alert.trigger_type == "customer_report":
        text = ("Customer, shown the transaction details, maintains they did not make it and still has the card"
                if denied else "Customer, shown the merchant and date, recognizes the transaction and withdraws the dispute")
    else:
        text = ("Customer states they did not make this transaction and still has the card"
                if denied else "Customer confirms they made this transaction")
    return (Reply.DENIED if denied else Reply.CONFIRMED), text


def update(p, reply):
    odds = p / (1 - p) if p < 1 else 1e6
    odds = odds * REPLY_ODDS if reply == Reply.DENIED else odds / REPLY_ODDS
    return round(odds / (1 + odds), 3)


def answer_file(alert, a, amounts, usage, steps):
    """Assemble the README answer format from an assessment."""
    initial_pol = to_policy(a, alert, amounts)
    initial_actions = policy.actions(initial_pol)
    evidence = list(a["evidence"])
    requests = []
    final_p = a["fraud_probability"]
    final_pol = initial_pol

    if policy.needs_evidence(initial_pol):
        reply, text = simulate_reply(final_p, alert)
        requests.append({"type": "customer_validation", "asked_after_step": steps, "assumed_response": text})
        final_p = update(final_p, reply)
        evidence.append({"claim": text, "source": "customer", "ref": "evidence_request:1", "entity_ids": []})
        final_a = dict(a, fraud_probability=final_p)
        if reply == Reply.CONFIRMED:
            final_a["affected_txn_ids"] = []
        final_pol = to_policy(final_a, alert, amounts, reply=reply)
        final_pol.independent_evidence += 1
        final_actions = policy.actions(final_pol)
    else:
        final_actions = initial_actions

    verdict = policy.verdict(final_pol)
    legit = verdict == "legitimate" or final_pol.reply == Reply.CONFIRMED
    affected = [] if legit else (a["affected_txn_ids"] or [alert.flagged_txn_id])
    exposure = 0.0 if legit else round(sum(abs(amounts.get(t, 0.0)) for t in affected), 2)
    names = [x["action"] for x in final_actions]
    status = ("closed_legitimate" if legit else "closed_fraud" if verdict == "fraud"
              else "escalated" if "ESCALATE_TO_ANALYST" in names else "open")
    stop, stop_reason = policy.should_stop(final_pol)
    report, report_reason = policy.file_report(final_pol)
    report = report and "FILE_REPORT" in names

    what_changed = "nothing"
    if requests:
        what_changed = (f"Simulated customer reply moved fraud probability from {a['fraud_probability']:.2f} to {final_p:.2f}; "
                        f"actions changed from {[x['action'] for x in initial_actions]} to {names}.")

    return {
        "case_id": alert.case_id,
        "case": {
            "status": status,
            "verdict": "legitimate" if legit else verdict,
            "fraud_probability": final_p,
            "pattern": "none" if legit else a["pattern"],
            "pattern_description": "" if legit else a["pattern_description"],
            "affected_txn_ids": affected,
            "first_suspicious_txn_id": "" if legit else (a["first_suspicious_txn_id"] or alert.flagged_txn_id),
            "connected_card_ids": [] if legit else a["connected_card_ids"],
            "connected_device_profiles": [] if legit else a["connected_device_profiles"],
            "exposure_usd": exposure,
            "evidence": evidence,
            "similar_prior_cases": a["similar_prior_cases"],
            "summary": a["summary"],
            "written_to_graph": False,
            "graph_case_id": "",
        },
        "evidence_requests": requests,
        "next_best_actions": {"initial": initial_actions, "final": final_actions, "what_changed": what_changed},
        "sar": {
            "file": report,
            "reason": report_reason,
            "narrative": "",
            "subjects": [],
            "total_amount_usd": exposure if report else 0,
            "activity_dates": [],
        },
        "stop_reason": stop_reason or "Further steps are unlikely to change the decision under the policy.",
        "tool_calls": usage.tool_calls,
        "tokens": usage.tokens,
        "latency_s": round(usage.seconds, 1),
        "_initial_probability": a["fraud_probability"],
    }

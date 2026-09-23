"""Suspicious activity report narrative, written only when FILE_REPORT is recommended.

Facts that can be looked up (dates, amounts, cards, devices, subjects) come
from the data, not the model. The model only writes the prose, from the case
it already built, to the README's standard: who, what, when, where, how, and
why it is suspicious, in six to twelve sentences that stand on their own.
"""

import pandas as pd

from graphite import data, llm

GUIDE = """Write the narrative section of a Suspicious Activity Report for a bank regulator.
It must stand on its own for a reader who has seen nothing else. In six to twelve plain sentences cover:
WHO: the customer, the cards, any device profiles and other customers or cards involved (use the exact IDs given).
WHAT: the activity and the total suspicious amount.
WHEN: the dates and times.
WHERE: the channel (online or in person) and billing regions.
HOW: how the activity was carried out.
WHY it is suspicious: the specific evidence, including links to other cases or cards.
State facts only; do not speculate beyond the evidence. Plain text, no headings, no bullet points."""


def facts(answer, alert):
    case = answer["case"]
    txns = case["affected_txn_ids"] or [alert.flagged_txn_id]
    rows = [data.alert_record(t) for t in txns]
    dates = sorted(pd.Timestamp(r["ts"]) for r in rows)
    return {
        "txns": rows,
        "total": round(sum(abs(r["amount"]) for r in rows), 2),
        "dates": [dates[0].strftime("%Y-%m-%d"), dates[-1].strftime("%Y-%m-%d")],
        "subjects": sorted({alert.customer_id, alert.card_id, *case["connected_card_ids"], *case["connected_device_profiles"]}),
    }


def write(answer, alert, usage):
    case = answer["case"]
    f = facts(answer, alert)
    lines = [
        f"Customer {alert.customer_id}, card {alert.card_id}. Verdict {case['verdict']}, pattern {case['pattern']}.",
        f"Pattern description: {case['pattern_description']}" if case["pattern_description"] else "",
        f"Summary: {case['summary']}",
        f"Suspicious transactions (total ${f['total']:,.2f}, {f['dates'][0]} to {f['dates'][1]}):",
        *[f"  {r['txn_id']} {r['ts']} ${r['amount']:.2f} {r.get('channel', '')} region {r.get('billing_region', '-')}"
          + (f" device [{r['device']}] {r.get('device_seen', '')}" if r.get("device") else "")
          + (f" via {r['proxy']}" if r.get("proxy") else "") for r in f["txns"][:15]],
        f"Connected cards: {', '.join(case['connected_card_ids'][:20]) or 'none'}",
        f"Connected device profiles: {', '.join(case['connected_device_profiles']) or 'none'}",
        f"Prior cases cited: {', '.join(case['similar_prior_cases']) or 'none'}",
        "Evidence:",
        *[f"  - {e['claim']}" for e in case["evidence"]],
    ]
    msg = llm.chat([{"role": "system", "content": GUIDE},
                    {"role": "user", "content": "\n".join(x for x in lines if x)}], usage, max_tokens=900)
    answer["sar"].update({
        "narrative": (msg.content or "").strip(),
        "subjects": f["subjects"],
        "total_amount_usd": f["total"],
        "activity_dates": f["dates"],
    })
    return answer

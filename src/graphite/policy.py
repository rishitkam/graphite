"""Fraud Policy v1.0 from the dataset README, as a pure function.

No model output reaches this module. It reads a structured Assessment and
returns actions with approval routes. All three pipelines share it, so any
difference in their scores comes from what they found, not how they turned
findings into actions.
"""

from dataclasses import dataclass, field
from enum import Enum

AUTO = "auto"
L1 = "L1"
L2 = "L2"

AUTO_ACTIONS = {
    "ALLOW_TRANSACTION", "MONITOR_CARD", "MONITOR_CONNECTED_CARDS", "WARN_CUSTOMER",
    "VERIFY_WITH_CUSTOMER", "STEP_UP_AUTH", "GENERATE_REPORT", "CREATE_CASE",
    "ESCALATE_TO_ANALYST", "CLOSE_NO_FRAUD",
}

STOP_HIGH = 0.85
STOP_LOW = 0.15
CASE_THRESHOLD = 0.30
WEAK_SIGNAL_CEILING = 0.70


class Reply(str, Enum):
    NONE = "none"            # nothing asked yet
    DENIED = "denied"
    CONFIRMED = "confirmed"
    NO_REPLY = "no_reply"    # asked, 24h passed


@dataclass
class Assessment:
    fraud_probability: float
    exposure_usd: float
    independent_evidence: int
    pattern: str = "none"
    customer_disputed: bool = False      # customer_report trigger
    reply: Reply = Reply.NONE
    recurring_match: bool = False        # R7: dispute matches own monthly pattern
    shared_origin: str = ""              # R6: named shared device / region / email
    connected_cards: list = field(default_factory=list)
    card_testing: bool = False           # R5 sequence observed
    large_purchase_cleared: bool = False # R5: >$100 already went through
    coordinated: bool = False            # R9: repeated abuse across customers
    customer_cards_confirmed_fraud: int = 0
    credentials_compromised: bool = False
    evidence_conflicts: bool = False


def route(action, exposure):
    if action in AUTO_ACTIONS:
        return AUTO
    if action == "DECLINE_TRANSACTION":
        return L1
    if action == "BLOCK_CARD":
        return L1 if exposure <= 2500 else L2
    return L2  # BLOCK_ALL_CARDS, FILE_REPORT


def verdict(a):
    if a.fraud_probability >= STOP_HIGH:
        return "fraud"
    if a.fraud_probability <= STOP_LOW:
        return "legitimate"
    return "uncertain"


def should_stop(a):
    """Section 6. Returns (stop, reason)."""
    if a.reply in (Reply.DENIED, Reply.CONFIRMED):
        return True, "verification response settled the question"
    decisive = a.fraud_probability >= STOP_HIGH or a.fraud_probability <= STOP_LOW
    if decisive and a.independent_evidence >= 2:
        return True, f"probability {a.fraud_probability:.2f} backed by {a.independent_evidence} independent pieces of evidence"
    if a.reply == Reply.NO_REPLY:
        return True, "no reply within 24 hours, acting under R4"
    return False, ""


def needs_evidence(a):
    stop, _ = should_stop(a)
    return not stop and a.reply == Reply.NONE


def file_report(a):
    """Section 3a. Returns (file, reason)."""
    strongly_suspected = a.fraud_probability >= WEAK_SIGNAL_CEILING or a.reply == Reply.DENIED
    if not strongly_suspected:
        return False, "fraud not confirmed or strongly suspected, 3a"
    if a.pattern == "undocumented" or a.coordinated:
        return True, "coordinated or undocumented pattern, R9 and 3a"
    if a.shared_origin:
        return True, f"shared origin {a.shared_origin}, R6 and 3a"
    if a.exposure_usd > 1000:
        return True, f"exposure ${a.exposure_usd:,.2f} exceeds $1,000, 3a"
    if a.connected_cards:
        return True, "connects to another card's fraud, R2 and 3a"
    return False, "no report threshold in 3a met, case only"


def actions(a):
    """Ordered actions with routes and rule citations."""
    out = []

    def add(action, reason):
        if all(x["action"] != action for x in out):
            out.append({"action": action, "route": route(action, a.exposure_usd), "reason": reason})

    asking = needs_evidence(a)
    p = a.fraud_probability

    if a.reply == Reply.CONFIRMED:
        add("CLOSE_NO_FRAUD", "R3: customer confirmed the transaction")
        return out

    if a.customer_disputed and a.recurring_match:
        add("CREATE_CASE", "R7: disputed charge")
        add("VERIFY_WITH_CUSTOMER", "R7: matches the customer's own recurring pattern")
        add("WARN_CUSTOMER", "R7: remind customer of the recurring charge, do not block")
        return out

    if a.card_testing:
        if a.large_purchase_cleared:
            add("BLOCK_CARD", "R5: testing sequence and a purchase over $100 already cleared")
        add("DECLINE_TRANSACTION", "R5: testing sequence observed")
        add("STEP_UP_AUTH", "R5: testing sequence observed")

    if a.reply == Reply.DENIED:
        add("BLOCK_CARD", "R2: customer denied the transaction")
        add("CREATE_CASE", "R2")
    elif a.reply == Reply.NO_REPLY:
        add("MONITOR_CARD", "R4: no reply within 24 hours")
        add("DECLINE_TRANSACTION", "R4: decline pending authorizations")
        if a.exposure_usd > 500:
            add("ESCALATE_TO_ANALYST", "R4: no reply and exposure over $500")
    elif asking:
        if p >= CASE_THRESHOLD or a.customer_disputed:
            add("CREATE_CASE", "3a: evidence requested" if not a.customer_disputed else "3a: customer dispute")
        weak = a.independent_evidence <= 1 and p < WEAK_SIGNAL_CEILING
        add("VERIFY_WITH_CUSTOMER", "R1: single signal below 0.70, verify before blocking" if weak
            else "3b: probability uncertain, verify before deciding")
    elif verdict(a) == "fraud":
        add("CREATE_CASE", "3a: fraud probability above 0.30")
        add("BLOCK_CARD", f"probability {p:.2f} with {a.independent_evidence} independent pieces of evidence")
    elif verdict(a) == "legitimate":
        add("ALLOW_TRANSACTION", f"probability {p:.2f} with {a.independent_evidence} independent pieces of evidence")
        add("CLOSE_NO_FRAUD", "evidence supports a legitimate transaction")

    if a.shared_origin:
        add("CREATE_CASE", f"R6: shared origin {a.shared_origin}")
        add("MONITOR_CONNECTED_CARDS", f"R6: every card sharing {a.shared_origin}")

    if a.pattern == "undocumented" and a.coordinated:
        add("CREATE_CASE", "R9: undocumented coordinated abuse")
        add("ESCALATE_TO_ANALYST", "R9: undocumented coordinated abuse")

    if verdict(a) == "uncertain" and (a.exposure_usd > 500 or a.evidence_conflicts):
        add("ESCALATE_TO_ANALYST", "R8: uncertain with exposure over $500 or conflicting evidence")

    if (a.customer_cards_confirmed_fraud >= 2 or a.credentials_compromised) and a.reply != Reply.NONE:
        add("BLOCK_ALL_CARDS", "R10: two or more cards confirmed or credentials compromised")

    report, why = file_report(a)
    if report and not asking:
        add("FILE_REPORT", why)

    return out

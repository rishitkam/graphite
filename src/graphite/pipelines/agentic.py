"""Tier 3: Agentic GraphRAG.

Same graph queries and the same evidence rendering as tier 2. What's added is
agency: the model starts with only the alert, the flagged transaction and the
card's baseline, and decides what else to look at, in what order, and when it
has seen enough. It can follow leads (inspect other transactions, check other
customers on a shared device, search precedent with its own query) and must
test the innocent explanation before concluding. Cheap cases stay cheap;
tokens go where the uncertainty is.
"""

import json

from graphite import assess, data, evidence, llm
from graphite import graph_tools as g
from graphite.pipelines import rag

MAX_ROUNDS = 4

AGENT = assess.SYSTEM.split("Return this JSON")[0] + assess.MEMORY_GUIDE + """

How you work:
- You start with the alert, the flagged transaction and the card's baseline. Call tools to get more. Several tools can be called in one turn.
- situation_memory is usually the first thing worth checking: it gives the base rate you should anchor on.
- Each tool costs time and tokens. Call what would change your assessment, not everything. Stop as soon as the answer is clear.
- Before concluding, name the most likely innocent explanation and check it (for example: were past alerts like this cleared, is this device or region just common, is this the cardholder's own pattern).
- When you are done, make no tool calls and reply with only the final JSON:""" + assess.SYSTEM.split("Return this JSON")[1]


def _tool(name, desc, **props):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": {k: {"type": v} for k, v in props.items()},
                       "required": list(props)}}}


TOOLS = [
    _tool("card_activity", "Every transaction on a card in the hours before the investigation time, with device, proxy and email flags.",
          card_id="string", hours_before="integer"),
    _tool("device_profile", "Who else used a device profile: customers, New-to-account and proxy rates, confirmed fraud through it, against the bank-wide base rate.",
          device="string"),
    _tool("customer_history", "A customer's cards and their prior closed fraud cases.", customer_id="string"),
    _tool("structural_precedent", "Closed cases sharing the same device or billing region as a transaction, weighted by how rare the shared link is.",
          txn_id="string"),
    _tool("situation_memory", "How past alerts in the most similar graph situation ended (channel, device novelty, familiarity, velocity), from vector search over case memory. Best single check of the base rate for an alert like this one.",
          txn_id="string"),
    _tool("search_cases", "Search closed case narratives by text, for precedent on a specific hypothesis.", query="string"),
    _tool("transaction", "Full detail of one transaction.", txn_id="string"),
    _tool("search_policy", "Search the bank's fraud policy and pattern definitions (rules R1 to R10, case vs report, stopping) for the text that applies. Cite what you find as a document source.",
          query="string"),
]


class Session:
    def __init__(self, alert, t_end, exclude):
        self.alert, self.t_end, self.exclude = alert, t_end, exclude
        self.known = {alert.flagged_txn_id, alert.card_id, alert.customer_id}
        self.device_result = None

    def call(self, name, args):
        a = self.alert
        try:
            if name == "card_activity":
                t = g.txn_detail(a.flagged_txn_id) if args["card_id"] == a.card_id else None
                hours = min(max(int(args.get("hours_before", 72)), 1), 720)
                if t is None:
                    rows = g.card_window(args["card_id"], self.t_end, max(1, hours // 24))
                    self.known |= {r["txn_id"] for r in rows}
                    return "\n".join(f"{r['txn_id']} {r['ts']} ${float(r['amount']):.2f} {r.get('channel', '')} {r.get('product_cd', '')} "
                                     f"region {r.get('addr1', '')} {r.get('device_seen', '')} {r.get('proxy', '')}" for r in rows[-20:]) or "no transactions"
                rows, lines = evidence.recent(t, self.t_end, hours=hours, max_rows=20)
                self.known |= {r["txn_id"] for r in rows}
                return "\n".join(lines)
            if name == "device_profile":
                d, lines = evidence.device({"device": args["device"], "card_id": a.card_id}, self.t_end, self.exclude)
                if d and self.device_result is None:
                    self.device_result = d
                if d:
                    self.known |= {args["device"]} | set(d["confirmed_fraud_cases_on_device"]) | set(d["customers_in_window"]) | set(d["card_ids_in_window"])
                return "\n".join(lines)
            if name == "customer_history":
                o, lines = evidence.customer(args["customer_id"], self.t_end, self.exclude)
                self.known |= {args["customer_id"]} | set(o["cards"]) | {c["case_id"] for c in o["prior_cases"]}
                return "\n".join(lines)
            if name == "structural_precedent":
                hits, lines = evidence.precedent(args["txn_id"], self.t_end, self.exclude)
                self.known |= {h["case_id"] for h in hits}
                return "\n".join(lines)
            if name == "situation_memory":
                if args["txn_id"] != a.flagged_txn_id:
                    return "situation memory is computed for the flagged transaction"
                hits, lines = evidence.situation_memory(a.flagged_txn_id, self.t_end, self.exclude)
                self.known |= {h["case_id"] for h in hits}
                return "\n".join(lines)
            if name == "search_cases":
                hits = rag.retrieve(str(args["query"]), self.t_end, self.exclude)
                self.known |= {h["case_id"] for h in hits}
                return "\n".join(f"{h['case_id']} [{h['outcome']}, {h['pattern']}]: {h['notes'][:170]}" for h in hits)
            if name == "search_policy":
                hits = g.search_policy(rag.embed(str(args["query"])), 3)
                return "\n".join(f"[{h['doc_id']}] {h['title']}: {h['body'][:400]}" for h in hits)
            if name == "transaction":
                if args["txn_id"] not in self.known:
                    return "unknown transaction id: only inspect transactions you have seen in evidence"
                t, line = evidence.flagged(args["txn_id"])
                if t["ts"] > self.t_end:
                    return "that transaction is after the investigation time"
                self.known |= {t["card_id"]} | ({t["device"]} if t["device"] else set())
                return line.replace("FLAGGED", "TRANSACTION")
        except Exception as e:
            return f"tool error: {e}"
        return f"unknown tool {name}"


def run(alert, t_end, exclude):
    usage = llm.Usage()
    s = Session(alert, t_end, exclude)
    t, flag_line = evidence.flagged(alert.flagged_txn_id)
    _, base = evidence.baseline(t, t_end)
    usage.tool_calls += 2
    if t["device"]:
        s.known.add(t["device"])

    messages = [
        {"role": "system", "content": AGENT},
        {"role": "user", "content": "\n".join([f"ALERT ({alert.trigger_type}): {alert.trigger_text}",
                                               f"Investigation time: {t_end}", flag_line] + base)},
    ]
    steps = []
    raw = None
    for _ in range(MAX_ROUNDS):
        msg = llm.chat(messages, usage, tools=TOOLS, max_tokens=1500)
        calls = msg.tool_calls or []
        if not calls:
            try:
                raw = llm.parse_json(msg.content or "")
            except ValueError:
                raw = None
            break
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [{"id": c.id, "type": "function",
                                         "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                        for c in calls]})
        for c in calls:
            try:
                args = json.loads(c.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = s.call(c.function.name, args)
            usage.tool_calls += 1
            steps.append({"tool": c.function.name, "args": args})
            messages.append({"role": "tool", "tool_call_id": c.id, "content": result[:2500]})

    if raw is None:
        # Out of rounds, or the answer wasn't valid JSON: ask once more, plainly.
        messages.append({"role": "user", "content": "Give your final assessment now as JSON in exactly this format:\n"
                         + assess.SYSTEM.split("Return this JSON")[1]})
        raw = llm.parse_json(llm.chat(messages, usage, json_mode=True).content)
    a = assess.link_ring_cards(assess.clean(raw, s.known), alert, s.device_result)
    return a, usage, {"steps": steps}

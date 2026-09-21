---
lens: "Read it like a judge — reverse-engineer what's actually being rewarded"
date: 2026-09-21
rule of engagement: written cold from the brief only, before opening any production/systems concerns
---

# Pass 1 — What is this hackathon actually testing?

## The single biggest reframe: there is no fraud label

> "Every transaction includes a risk score from the bank's fraud detection model. There is no 'Is Fraud' flag."

This one sentence changes the entire nature of the task. Without a ground-truth label, "Investigation
accuracy — 25%" **cannot** be measured as precision/recall against a held-out label. It has to be judged
qualitatively — did the agent's evidence, reasoning, and case file read like a competent fraud investigation?

That means this is not a Kaggle-style classification contest wearing an agent costume. It's closer to being
graded like a **case-file audit**. A team that builds a great gradient-boosted fraud classifier and bolts an
LLM on top to narrate its output will score worse than a team with a mediocre classifier but a legible,
well-evidenced, policy-citing investigation trail — because 60% of the rubric (investigation accuracy + next
best action + explainability) is about the *trace*, not the *verdict*. The verdict is graded through the trace.

## Traps hidden in the phrasing

1. **"Not every fraud pattern present in the data is documented."**
   This is a deliberate generalization test. Five typologies are given; the benchmark cases almost certainly
   include at least one that doesn't cleanly match any of the five. A submission that is really just
   `if pattern matches typology_1..5: else: shrug` will visibly fail on those cases. The graph-algorithm
   requirement (community detection, traversal, "relationship analysis") exists specifically so unlabeled,
   undocumented patterns can still surface via structure (shared devices/emails/rings) rather than
   pattern-matching against a fixed list.

2. **The submission format demands the recommendation *twice* per case:**
   > "The next best action and required approval route recorded: before any additional evidence is requested /
   > after any additional evidence is received."
   This is easy to skim past, but it's a hard schema requirement: the agent's output artifact must show its
   mind changing. A one-shot pipeline (gather everything → decide once) structurally cannot produce this
   field. The architecture has to have a real checkpoint where a provisional decision is committed *before*
   evidence-gathering, separate from the revised decision *after*. This is graded under "Next best action —
   25%" via the phrase "updates its recommendation as new evidence becomes available."

3. **"The case should also be written to the graph"** is a separate bullet from "the internal investigation
   record." It's easy to build a nice case object in application memory/Postgres and forget that TigerGraph
   itself needs to persist the case, evidence, and decision as first-class vertices/edges — otherwise "case
   memory" (retrieving similar past cases via the graph) has nothing to retrieve from for future runs, and the
   graph-native storytelling judges are expecting to see in the demo won't exist.

4. **TigerGraph MCP is listed under "Required components," not optional.** Combined with "Agentic design and
   engineering — 15%: quality of ... tool use," this suggests judges want to *see* the agent calling graph
   capabilities as tools through MCP, not just an app that happens to query TigerGraph with a driver behind the
   scenes. The MCP boundary is itself part of what's being evaluated (tool selection, tool contracts), not
   incidental plumbing.

5. **"Actions ... may be simulated, stubbed, or represented through mock APIs."** This is explicit permission
   to *not* burn hackathon time on real Twilio/email/CRM integrations. Judges are scoring the decision and
   control layer (what got decided, what approval it needed, why), not whether a real SMS actually sent. Time
   spent wiring real third-party APIs is time taken from the parts that are actually graded.

6. **"If you use Savanna, ensure auto-stop and auto-start are enabled."** A throwaway ops note, but it implies
   the organizers have seen teams show up to demo day with a dead/expired cloud instance. Worth treating as a
   real pre-demo checklist item, not a footnote.

7. **"External sources should complement the TigerGraph-based investigation"** (not replace it). A design that
   leans on an LLM's own world knowledge or an external fraud API as the primary judgment, with the graph as
   a data source the LLM occasionally glances at, will likely underperform on "Innovation — 15%: originality
   ... use of graph" even if its final answers are fine. The graph needs to do real inferential work
   (traversal, propagation, community structure), not just supply rows.

## What the weight distribution implies

- Investigation accuracy (25) + Next best action (25) = **50%** rides entirely on the quality of reasoning on
  the 20 benchmark cases specifically — not on infrastructure elegance.
- Agentic design & engineering (15) + Innovation (15) = **30%** rides on architecture: memory, tool use,
  controls, permissions, and something genuinely novel in how graph + AI + GraphRAG are combined.
- Case summary/explainability (10) + Demo quality (10) = **20%** rides on communication, not new capability.

A team that over-invests in infrastructure polish and under-invests in producing sharp, well-evidenced
per-case reasoning is capped near 50% regardless of how good the engineering looks. Conversely, a team with
excellent reasoning but an unclear demo or unreadable case summaries leaves 20% on the table for something
that's pure presentation work, not research.

## Underlying tone

"Defensible action" appears twice. Combined with the emphasis on policy, approval routes, and a Suspicious
Activity Report "when required by policy," the brief reads like it was written with a compliance/audit
sensibility, not a pure-ML one. That suggests judges (or at least the rubric's authors) will respond well to
an audit trail that could survive a regulator asking "why did the system do this," more than to a marginally
higher hit rate that can't explain itself.

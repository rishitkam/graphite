# Graphite — an agentic fraud investigator built on TigerGraph

*Built from [thought-pass-1-rubric-lens.md](thought-pass-1-rubric-lens.md),
[thought-pass-2-systems-lens.md](thought-pass-2-systems-lens.md), and their
[synthesis](thought-comparison-synthesis.md). Follows the standard system-design framework: requirements →
high-level design → deep dive → scale/reliability → trade-offs.*

## The one-paragraph pitch

Fraud evidence, like a pencil sketch, gets darker as you add strokes — not certain in one stroke, not needing
a finished portrait to be recognizable. Graphite treats every investigation as a sketch that starts faint (a
raw signal) and darkens as evidence accumulates (each fact is a stroke), stops the moment the sketch is
*dark enough to act on defensibly* rather than waiting for a finished portrait, and files the sketch itself —
not just the verdict — as the case record. The name and metaphor aren't decoration: they map directly onto
the two hardest parts of the brief — visualizing uncertainty, and knowing when to stop investigating.

---

## 1. Requirements

### Functional (from the brief, restated as commitments)
- Open a case from three trigger types (risk score, customer report, analyst request) and de-duplicate
  concurrent triggers on the same entity.
- Traverse the graph for connected evidence: transactions, devices, IPs, shared identifiers, prior cases.
- Detect fraud patterns beyond the five documented typologies (structural/graph-native, not just rule-matching).
- Maintain a case as a living record: evidence, findings, risk assessment, and **two** recommendation
  checkpoints — one before requesting more evidence, one after receiving it.
- Request additional evidence only through controlled, policy-approved actions.
- Recommend and optionally execute one or more next actions, gated by an approval-route policy.
- Decide when to stop investigating.
- Explain evidence, uncertainty, and reasoning in a case summary, plus a SAR when policy requires one.
- Store and retrieve case memory to inform future investigations, and update it as cases resolve.
- Present all of the above through a usable interface.

### Non-functional
- **Auditability over cleverness.** Every executed action must be traceable to a rule + evidence, not to an
  LLM's free-text judgment, because the deliverable includes a compliance artifact (SAR) and an approval
  route, both of which need to survive a "why did it do that" question.
- **Latency that doesn't degrade demo-to-demo.** Opening a case should feel like a lookup, not a batch job —
  achieved by precomputing expensive graph analytics rather than computing them per request (pass 2, §4).
- **Safety against untrusted content.** Any text sourced from transaction/merchant fields or retrieved
  documents is evidence to reason about, never instructions to act on (pass 2, §6).
- **Extensibility without redeploying.** New typologies and policy changes should be data (graph vertices /
  policy documents), not code changes, since "not every pattern is documented" implies typologies will grow.
- **Cost hygiene.** Savanna auto-stop/auto-start honored; no component assumes an always-on paid cloud service.

### Constraints
- Hackathon timeline → prefer an existing agent framework (LangGraph fits the explicit state-machine shape
  of the required flow) over a bespoke orchestrator; use TigerGraph MCP as the tool boundary since it's a
  required, separately-graded component; stub side-effecting actions per the brief's explicit permission.
- Dataset is static/historical (batch), not a live transaction stream — the design should not *require*
  streaming infrastructure, but shouldn't structurally preclude it either.

---

## 2. High-level design

```
                              ┌───────────────────────────────────────────┐
                              │                 TRIGGERS                   │
                              │   risk-score event · customer report ·     │
                              │   fraud-analyst request                    │
                              └───────────────────┬─────────────────────────┘
                                                   ▼
                              ┌───────────────────────────────────────────┐
                              │   INTAKE / DEDUP   —  "the tip line"       │
                              │   normalize → InvestigationTrigger         │
                              │   entity-lock check: is there already an   │
                              │   OPEN case touching this account/card?    │
                              │     yes → attach as new evidence           │
                              │     no  → open a Case vertex               │
                              └───────────────────┬─────────────────────────┘
                                                   ▼
   ┌─────────────────────────────────────────────────────────────────────────────────────┐
   │                     ORCHESTRATOR  —  "the detective"  (LangGraph)                     │
   │                                                                                       │
   │   Open ─► Sketch (hypotheses+confidence) ─► Value-of-Info check ─┬─► Decide           │
   │              ▲                                                  │                     │
   │              └──────────────── Gather more evidence ◄───────────┘ (loop while worth it)│
   │                                                                     │                  │
   │                                                          Decide ─► Explain ─► File     │
   │                                                                        │               │
   │                                                              Update case memory        │
   └───────┬────────────────────────────┬──────────────────────────────────┬───────────────┘
           │ read-only tools (MCP)      │ propose (LLM output only)        │ execute (never LLM-direct)
           ▼                            ▼                                  ▼
 ┌───────────────────────┐   ┌────────────────────────────┐   ┌─────────────────────────────┐
 │  TIGERGRAPH MCP        │   │  POLICY / APPROVAL ENGINE   │   │  ACTION EXECUTORS (stubs)     │
 │  get_account_graph     │◄──┤  — "the rulebook" —         │──►│  hold txn · block/monitor      │
 │  get_ring_membership   │   │  deterministic, no LLM      │   │  account · step-up auth ·      │
 │  get_similar_cases     │   │  in the loop. Reads          │   │  notify customer · file SAR ·  │
 │  run_pattern_query     │   │  structured fields only.     │   │  escalate to analyst           │
 │  request_evidence(...) │   │  Issues an approval ticket   │   │  (mock/simulated per brief)    │
 └───────────┬────────────┘   │  or routes to human review.  │   └─────────────────────────────┘
             ▼                └────────────────────────────┘
 ┌───────────────────────────────────────────────────────────────────────────────────────┐
 │                          TIGERGRAPH  —  "the archive"                                    │
 │  raw: Customer, Account, Card, Transaction, Device, IPAddress, Merchant                  │
 │  derived (scheduled batch): SHARES_DEVICE / SHARES_EMAIL / SHARES_IP edges,               │
 │                             ring_id + propagated_risk_score (Louvain + seeded PPR)         │
 │  case layer: Case, EvidenceItem, Action, AnalystDecision, PolicyClause, FraudTypology      │
 │  memory: Case—SIMILAR_TO—Case (hybrid structural+semantic, precomputed + query-time)       │
 └───────────────────────────────────────────────────────────────────────────────────────┘
             ▲
             │ approve / override, written back as AnalystDecision
 ┌───────────────────────────────────────────────────────────────────────────────────────┐
 │      ANALYST UI — "the sketch"                        CALIBRATION JOB — "the debrief"    │
 │      case list · account neighborhood rendered         periodically compares agent        │
 │      as a sketch that darkens with evidence ·           recommendations vs analyst         │
 │      pencil-draft vs inked-verdict view ·               outcomes, adjusts stopping-rule     │
 │      precedent agree/disagree panel                     cost estimates and escalation rate  │
 └───────────────────────────────────────────────────────────────────────────────────────┘
```

### The core loop, mapped to the brief's 8-step flow

| Brief's step | Graphite's name | What actually happens |
|---|---|---|
| 1. Trigger | *Open the file* | Intake dedups against open cases per entity; opens or attaches to a `Case` vertex. |
| 2. Investigate | *Walk the graph* | MCP read-tools pull the account neighborhood, ring membership, precomputed risk. |
| 3. Gather evidence | *Take statements* | Structured evidence assembled into a `Sketch` object: candidate typologies + confidence + open questions. |
| 4. Assess uncertainty | *Check the sketch* | Value-of-information check (§3.4) — is the sketch dark enough, or is it worth another stroke? |
| — checkpoint — | **Pencil draft** | First recommendation + approval route is committed here, *before* any extra evidence is requested — this is the brief's "before additional evidence" record. |
| 5. Gather more if needed | *Canvas for more* | Controlled evidence actions (step-up auth, ask analyst) run only if §3.4 says they're worth their cost. |
| 6. Take next action(s) | *Make the call* | Policy engine issues approval ticket(s); executors run (stubbed) for whatever's authorized. |
| — checkpoint — | **Inked verdict** | Second recommendation + approval route, *after* evidence returns — the brief's "after additional evidence" record. |
| 7. Explain | *Write it up* | Case narrative + evidence citations + policy clause citations; SAR generated if policy requires. |
| 8. Update memory | *File it* | Case, evidence, decision, and outcome written to the graph; similarity edges added for future retrieval. |

---

## 3. Deep dive

### 3.1 Graph data model

**Raw entity layer** (from the IEEE-CIS-derived dataset — "every original row and column kept"):
`Customer`, `Account`, `Card`, `Transaction`, `Device`, `IPAddress`, `Merchant`, plus whatever identity/device
columns the dataset's own README documents (the public IEEE-CIS schema splits these across a transaction table
and an identity table — `card1-6`, `addr1-2`, email domains, and `DeviceType`/`DeviceInfo`/`id_01-38` are the
fields that typically carry the entity-resolution signal; confirm exact column names against the HHGOA README
before building, since this package may rename or trim them).

**Derived layer** (built once, refreshed on a schedule — not computed per request):
- `SHARES_DEVICE`, `SHARES_EMAIL`, `SHARES_IP` edges between accounts, built by grouping on those
  near-identity keys — this is the standard entity-resolution move for this specific dataset shape (grouping by
  card+address+email-domain to approximate a real-world identity is a well-known technique against IEEE-CIS)
  and it's what turns "a pile of transactions" into "a graph a ring can hide in or be found in."
- `ring_id` and `propagated_risk_score` attributes on `Account`, computed by community detection (Louvain or
  weakly-connected-components over the derived edges) plus a seeded propagation (personalized PageRank seeded
  from accounts in confirmed-fraud closed cases) — this is what lets the system flag risk on an account that
  has *no* documented-typology match but sits one hop from a known-bad device.

**Case layer:** `Case`, `EvidenceItem`, `Action`, `AnalystDecision`, `PolicyClause`, `FraudTypology`, connected
by `HAS_EVIDENCE`, `MATCHES_PATTERN`, `CITES`, `RESULTED_IN`, `OVERRIDDEN_BY`, and `Case —SIMILAR_TO→ Case`
(weighted, see §3.5).

### 3.2 Tool contracts (TigerGraph MCP) — the propose/execute split

Two disjoint sets of MCP tools, deliberately asymmetric in trust:

- **Read tools** (LLM can call freely): `get_account_graph`, `get_ring_membership`, `get_transaction_path`,
  `get_similar_cases`, `run_pattern_query(typology_id)`, `search_policy(topic)`. These only ever return data.
- **Write tools** (LLM can never call directly): `execute_action(action, approval_ticket)`. The *only* way to
  obtain a valid `approval_ticket` is from the Policy/Approval Engine, which reads structured fields (exposure
  amount, confidence band, action type, customer risk tier) — never LLM free text — and either issues a ticket
  (auto-approved band), or returns "needs human approval," in which case the ticket only materializes after an
  analyst clicks approve in the UI.

This is the direct answer to both halves of Convergence A in the synthesis: it satisfies "only authorized
actions may be executed" as a literal schema/audit fact, and it closes the prompt-injection/hallucination hole
where a poisoned merchant-name field could otherwise talk the agent into acting — because the agent proposing
an action and the system executing one are separated by a gate that doesn't read prose.

### 3.3 The Sketch — hypothesis representation

Instead of a single fraud/not-fraud score, each case carries a `Sketch`:

```
Sketch {
  candidate_typologies: [{typology_id, support_evidence[], confidence}],
  overall_risk_band: LOW | MEDIUM | HIGH,
  open_questions: [ "what would most reduce uncertainty right now" ],
  precedent: {similar_case_id, agreement: AGREES | DISAGREES | NOVEL, why}
}
```

Confidence darkens (moves LOW→MEDIUM→HIGH) as evidence is added; it never resets to zero, matching how real
investigations accumulate rather than restart.

### 3.4 The stopping rule — value of information, not a threshold

A static "stop once confidence > 90%" throws away the fact that gathering evidence has a cost. Graphite
scores each *candidate* next evidence-gathering action against the cost of the delay it introduces:

```
for each candidate evidence action e (step-up auth, ask analyst, wait one more txn, ...):
    cost(e)  = friction_cost(e) + expected_wait_time(e) × ongoing_exposure_rate(account)
    value(e) = P(e resolves the open question) × (loss avoided by not acting on wrong info)

stop gathering when max_e [value(e) − cost(e)] ≤ 0
```

`ongoing_exposure_rate` is what makes this more than academic: for an account being actively drained, waiting
is expensive, so the rule favors an immediate *cheap, reversible* action (temporary hold, step-up prompt) taken
in parallel with continued investigation — while an irreversible action (permanently closing an account, filing
a SAR, denying a transaction outright) still requires the confidence bar that expensive evidence buys. Cost and
value estimates per evidence type are seeded from the closed-case dataset (e.g., historical median time an
analyst request took to resolve, and how often it changed the outcome) rather than hand-picked — and are the
one thing the calibration job (§3.6) is allowed to keep adjusting after launch.

This rule is what produces the **pencil draft** (committed the moment the stopping check first fires, before
any extra evidence is requested) and the **inked verdict** (committed after that evidence returns) — the two
checkpoints the submission format requires are a direct side-effect of the stopping rule's own bookkeeping,
not a separately bolted-on export step.

### 3.5 Case memory — hybrid GraphRAG with a disagreement signal

Two retrieval paths, merged and reranked, not just one vector search:
1. **Structural similarity** — shared devices/emails/IPs/ring membership with past cases (graph traversal;
   cheap, high-precision, catches same-ring recurrence even when the narrative text looks nothing alike).
2. **Semantic similarity** — embedding search over case narratives (catches same *modus operandi* described in
   different words, different merchant, different amount).

The merged result is required to name *which* shared entities or signals justify the match — not just a
similarity score — and the orchestrator explicitly checks whether its current sketch **agrees or disagrees**
with the precedent's outcome. Disagreement doesn't get silently overridden by precedent *or* silently
overrule it; it gets surfaced as its own line in the case summary ("similar to case #4471, which was cleared —
unlike that case, this one also shows a shared device with a confirmed-fraud account"). This is the direct
fix for pass 2's bias-inheritance concern, and it doubles as exactly the kind of explanation content the
case-summary/explainability criterion is scoring.

### 3.6 Explainability, SAR generation, and the calibration loop

- The case narrative cites specific evidence items and specific `PolicyClause` vertices (retrieved via
  GraphRAG over the policy/typology/regulatory documents included in the dataset) by clause ID — the SAR is
  assembled from those citations, not paraphrased from the model's general knowledge, so a compliance reader
  can trace every sentence back to a source.
- Every analyst approve/override is written back as an `AnalystDecision` edge on the `Action`. A scheduled
  **debrief** job periodically compares agent recommendation vs. analyst outcome and nudges the stopping
  rule's cost/value estimates and confidence bands — this is what keeps "use prior outcomes to inform
  recommendations" from being satisfied only in the shallow retrieval sense, and it's the direct answer to
  pass 2's alert-fatigue concern (over time, escalations should concentrate on genuinely hard cases).

### 3.7 UI — "the sketch," not a generic dashboard

The account neighborhood graph is literally rendered as a pencil sketch: edge and node opacity track evidence
strength, so a barely-suspicious account looks genuinely faint and a well-evidenced ring looks genuinely dark
— uncertainty is shown, not just stated. Alongside it: the pencil-draft vs. inked-verdict pair for the current
case, and the precedent agree/disagree panel from §3.5. This turns two separately-graded requirements (usable
interface; explainability) into one visual object instead of two disconnected screens.

---

## 4. Scale and reliability

- **Load shape:** ~590K transactions / ~13.5K customers is small enough that even fairly heavy graph
  algorithms run comfortably as a scheduled batch job (minutes, not hours) — the important discipline is
  running them *on a schedule and writing results back as attributes* rather than inline per request, which is
  what keeps a single case investigation feeling like a lookup instead of a batch job (pass 2, §4).
- **Concurrency / idempotency:** an `open_case_id` marker on the `Account` vertex is checked before opening a
  new case; a second trigger on an already-open account attaches as new evidence to the existing case instead
  of spawning a conflicting parallel investigation (pass 2, §5).
- **Staleness discipline:** every precomputed graph attribute (ring id, propagated risk) carries a
  `computed_at` timestamp that shows up in the case record, so a "6-hour-old" ring score is never presented as
  live truth. For the account currently under active investigation, a narrow, localized recompute (just that
  account's neighborhood) can run inline without the cost of a global recompute.
- **Failure handling:** if an evidence-gathering action (e.g., step-up auth) times out, that's treated as
  evidence itself ("customer did not respond within SLA") feeding back into the sketch, not as a system error
  to retry silently — an unresponsive customer is informative, not a bug.
- **Cost hygiene:** Savanna's auto-stop/auto-start honored; nothing in the design requires the graph database
  to be continuously warm outside of active development/demo windows.

---

## 5. Trade-off analysis

| Decision | Chosen | Alternative considered | Why |
|---|---|---|---|
| Orchestration | LangGraph explicit state machine | Role-based multi-agent (CrewAI-style) | The brief's flow is a strict sequence of named states (trigger→...→memory) with a real loop-back (gather more evidence); an explicit graph of states matches that shape more directly than a crew of loosely-coordinated role-agents, and makes the two recommendation checkpoints easy to pin to specific nodes. |
| Action authorization | Deterministic policy engine issues tickets; LLM never calls write tools | Let the agent call action tools directly with a confirmation prompt | A confirmation prompt still trusts the LLM's judgment about *which* action to propose from data that includes attacker-influenced text; separating propose from execute removes an entire class of hallucination/injection failure, at the cost of needing an explicit rules layer. |
| Fraud pattern detection | Precomputed graph structure (community detection + seeded propagation) underneath the five documented typologies | Rule-matching against the five typologies only | The brief states not every pattern is documented; structural detection generalizes to undocumented patterns, rule-matching doesn't. Cost: more upfront modeling work, and results that are probabilistic rather than crisply labeled. |
| Stopping rule | Value-of-information (cost vs. expected confidence gain) | Fixed confidence threshold | A threshold ignores that evidence-gathering has cost and that exposure is time-sensitive; VoI captures "act now cheaply, keep investigating" as a distinct option from "wait for certainty." Cost: needs cost/value estimates, approximated from historical case-resolution times rather than derived precisely. |
| Case memory retrieval | Hybrid structural + semantic, with an explicit agree/disagree check | Pure vector search over case narratives | Vector search alone conflates textual similarity with causal relevance and silently launders analyst bias; hybrid retrieval plus a disagreement check costs more engineering but produces both better matches and an explicit bias check. |
| Heavy graph algorithms | Scheduled batch, results cached as vertex attributes | On-demand computation per investigation | On-demand computation doesn't scale to interactive latency and reruns the same global computation for every case; batch costs a staleness window, mitigated by timestamping and localized recompute for the active account. |

---

## 6. Mapping back to the judging criteria

| Criterion | Weight | Primarily satisfied by |
|---|---|---|
| Investigation accuracy | 25% | Precomputed structural detection (rings, propagated risk) catching undocumented patterns; hybrid memory surfacing real precedent. |
| Next best action | 25% | Value-of-information stopping rule; pencil-draft/inked-verdict two-checkpoint record; propose/execute policy gate. |
| Case summary & explainability | 10% | Evidence- and clause-cited narrative; precedent agree/disagree panel; the sketch visualization itself. |
| Agentic design & engineering | 15% | LangGraph state machine matching the required flow; TigerGraph MCP as the literal tool boundary; deterministic approval gate as a control. |
| Innovation | 15% | Structural (not just typology) fraud detection; hybrid GraphRAG with disagreement surfacing; cost-aware stopping rule; sketch-as-uncertainty-visualization UI. |
| Demo quality | 10% | One visual object (the sketch) carries both the neighborhood graph and the case's evidentiary state, instead of separate disconnected screens. |

---

## 7. What we'd revisit with more time

- Replace deterministic key-matching entity resolution with real probabilistic record linkage.
- Replace the hand-seeded VoI cost estimates with a properly fit model against the full closed-case history.
- Add a fairness pass over memory-driven recommendations (is the system inheriting a skew from historical
  analyst decisions across any protected or proxy dimension?) — flagged as a risk in pass 2, not yet solved
  here, only guarded against via the disagreement signal.
- Move from scheduled-batch graph analytics toward incremental/streaming updates if this ever met a live
  transaction feed instead of a static historical dataset.
- Version the policy engine's rules like code (with review/audit trail), since it's the one component a
  regulator would actually want to inspect.

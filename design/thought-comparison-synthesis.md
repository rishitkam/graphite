---
compares: thought-pass-1-rubric-lens.md, thought-pass-2-systems-lens.md
date: 2026-09-21
---

# Comparing the two passes

Pass 1 asked "what is actually being rewarded." Pass 2 asked "where does this actually break." They were
written independently, on purpose — pass 2 was drafted without re-consulting pass 1's conclusions — so that
agreement between them means something, and disagreement surfaces a real blind spot rather than the same
thought said twice.

## Where they independently converged (highest-confidence signal)

**Convergence A — action execution needs a hard gate, for two different reasons.**
Pass 1 noticed this as a *grading/schema* fact: "only authorized actions may be executed," and the submission
format literally requires recording an approval route both before and after evidence is gathered. Pass 2
arrived at the same architectural requirement from a *safety* angle: an LLM that can call `block_account`
directly is one crafted merchant-name field away from a bad outcome, independent of whether it also happens
to be graded. Two unrelated reasons landing on the same conclusion — propose/execute must be separate, and
execution must run through a deterministic, non-LLM gate — is a strong signal that this isn't optional
polish, it's the load-bearing part of the architecture.

**Convergence B — case memory has to be more than a lookup.**
Pass 1 flagged this as an *innovation/rubric* opportunity: GraphRAG and relationship analysis across cases is
explicitly what's being scored under "originality of the approach and use of graph." Pass 2 flagged the same
component as a *risk*: naive retrieval-and-defer can silently launder analyst bias or retrieve superficial
matches. Both point at the same fix — retrieval has to justify *why* a precedent is relevant (shared entities,
shared structure) and the system must be able to state disagreement with precedent, not just cite it.

**Convergence C — the five documented typologies are a trap, not the whole task.**
Pass 1 read "not every fraud pattern present in the data is documented" as a deliberate generalization test
baked into how the benchmark cases were likely chosen. Pass 2, reasoning purely about engineering, arrived at
needing graph algorithms that detect structure (rings, propagated risk) rather than pattern-match against a
fixed list — for the unrelated reason that pattern-matching doesn't scale and doesn't generalize. Same
conclusion, reached from grading-strategy and from systems-engineering directions independently: typology
matching is a floor, not the ceiling, of what the fraud-detection layer should do.

## Where one pass caught something the other missed

**Only pass 1 caught:** the dual before/after recommendation checkpoint as a literal schema requirement on
the output file (easy to miss on a skim, and structurally impossible to satisfy with a single-pass pipeline);
the fact that MCP is graded as part of "agentic design," not incidental plumbing; that actions are explicitly
allowed to be stubbed (a time-allocation signal for a time-boxed hackathon); the Savanna auto-stop/auto-start
operational note; and the overall "this is graded like a case-file audit, not a Kaggle contest" reframing that
follows from there being no fraud label.

**Only pass 2 caught:** the cost-of-evidence / sequential-stopping-rule framing for "when is there enough
evidence" (arguably the single most substantive idea either pass produced — a static confidence threshold is
a materially weaker design than a real cost/benefit stopping rule); the concurrency/idempotency problem of two
triggers opening two conflicting cases on the same entity; the adversarial gameability of a fully transparent
deterministic policy; the staleness/scheduling requirement for heavy graph algorithms; and the alert-fatigue
feedback loop needed so the system's escalation rate actually improves instead of just routing forever.

## What this changes about the plan

Neither pass alone would have been enough. Optimizing only for pass 1 produces something that scores well on
a rubric but could be a fragile, gameable, occasionally-biased system underneath — technically compliant,
not actually good. Optimizing only for pass 2 produces a genuinely robust design that might still miss
concrete, easy-to-satisfy submission mechanics (like the before/after recommendation record) that cost real
points for no engineering reason. The system design below is built to satisfy both simultaneously: pass 1's
findings mostly shape *what artifacts the system must produce and when*; pass 2's findings mostly shape *how
the internals have to be built so those artifacts are trustworthy*.

Concretely, the synthesis drives four non-negotiable architectural commitments carried into the design:

1. A **propose/execute split with a deterministic policy gate** — the answer to both Convergence A angles.
2. A **hybrid structural + semantic case memory that can disagree with precedent** — the answer to
   Convergence B, and the mechanism that produces the "why this precedent is/isn't relevant" explanation text
   pass 1 identified as separately graded under case-summary/explainability.
3. A **typology-agnostic graph layer** (precomputed ring detection + propagated risk) sitting underneath, not
   instead of, the five documented typologies — Convergence C.
4. A **value-of-information stopping rule with a two-checkpoint recommendation record** (pencil draft before
   evidence, inked verdict after) — pass 2's strongest original idea, reshaped to also directly satisfy pass
   1's literal before/after schema requirement instead of being a separate internal-only mechanism.

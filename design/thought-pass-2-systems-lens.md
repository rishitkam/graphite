---
lens: "Set the rubric aside — where does this actually break as a real system?"
date: 2026-09-21
rule of engagement: written as a principal engineer / fraud-ops architect asked to red-team the design,
deliberately not re-reading pass 1's notes first, to keep the angle independent
---

# Pass 2 — Where does an agentic fraud investigator actually fail?

## 1. Base-rate blindness and benchmark overfitting

Fraud is rare — typically low single digits of transactions even in datasets curated to contain it. If any
threshold, prompt example, or "confidence cutoff" gets tuned by looking at the 20 benchmark cases, that's
overfitting to a hand-picked sample and it will not generalize. The 20 cases should be treated purely as a
held-out qualitative check the system never sees during development, not a validation set to iterate against.
A subtler version of this: fraud cases in the training material (the closed 4-month cases) were selected
*because* they were investigated — they are not a random sample of transactions. Any base rate or pattern
frequency learned from "closed cases" is conditioned on "stuff that already looked suspicious enough to open
a case," which is a biased slice of the real distribution. A system that quietly assumes the closed-case
mix reflects the true fraud/legit ratio will miscalibrate its own confidence.

## 2. Memory can encode and launder human bias

The brief wants the agent to "retrieve similar past cases" and "use prior case outcomes and analyst decisions
to inform recommendations." But those past outcomes are *human judgment calls*, not ground truth. If an
analyst cleared a case too quickly, or was systematically lenient on one merchant category, or a ring went
undetected for months before anyone connected the accounts, that shows up in memory as a "cleared" precedent.
An agent that leans on "a similar case was cleared, so clear this one" is not just risking an error — it's
mechanically reproducing and amplifying whatever mistakes or biases existed in the historical analyst
decisions, at scale, under the appearance of data-driven objectivity. The system needs a way to *disagree*
with precedent and say so, not just retrieve and defer to it.

## 3. A fully transparent, deterministic policy is gameable

Fraud is adversarial. If the acting population (fraud rings) can infer the system's thresholds — "stay under
$X to avoid step-up auth," "space transactions Y hours apart to avoid the velocity rule" — they will adapt to
them, because the same accounts get reused across attempts. Perfect explainability and perfect determinism
are in tension with robustness against an adaptive adversary. This doesn't mean "be less explainable to the
customer/regulator" — it means the *internal* decision boundaries shouldn't be so crisp and static that
they're trivially reverse-engineerable from the outside (e.g., via repeated probing), and some sampling-based
or randomized friction is worth considering even at small scale.

## 4. Heavy graph algorithms don't run for free, and they go stale

Community detection / connected-components / propagation over ~590K transactions and their device and IP
linkages is a real computation, not a free side-effect of "having a graph." If the agent tries to compute
these live, per investigation, response time will visibly degrade — bad in a demo, worse in production where
a live drain on an account needs a fast decision. The correct shape is: expensive global graph algorithms run
on a schedule (or incrementally on new-data arrival) and *write their output back onto the graph* as
attributes (ring id, propagated risk score) that the agent's per-case queries simply read. This also means the
system has to be honest about staleness — a ring score computed six hours ago is a snapshot, and the case
record should say so, rather than presenting a batch-computed number as if it were live truth.

## 5. Concurrency: nothing stops two triggers from opening two cases on the same account

If a fraud-score trigger and a customer report arrive for the same account within the same minute, a naive
system spins up two independent investigations that can reach two different conclusions on the same entity —
one thread says "block," another says "allow" — a real correctness bug, not just an edge case. Investigations
need to be **keyed and locked per entity** (e.g., an "open case" marker on the account vertex that new triggers
check before opening a duplicate), with new signals folded into the existing open case as new evidence instead
of spawning a parallel one.

## 6. Letting an LLM call action tools directly is a hallucination *and* prompt-injection risk

The design explicitly grounds the agent with retrieved context — graph data, policy documents, and (per the
brief) merchant/transaction metadata. Some of that text is attacker-influenced: a fraudster fully controls
fields like merchant name or a transaction memo. If those fields flow into the LLM's context and the LLM is
also the thing empowered to call `block_account` or `approve_refund`, a crafted string in a memo field becomes
a potential instruction-injection vector, on top of the ordinary risk of the model simply hallucinating a
plausible-sounding but wrong tool call. Retrieved data — from the graph, from documents, from transaction
fields — has to be treated strictly as evidence to reason *about*, never as instructions to act *on*. The
system is safer if the LLM can only ever *propose* actions, and a separate deterministic component, driven off
structured fields it controls (not free text), is the only thing that can actually authorize execution.

## 7. "When to stop investigating" is a cost/stopping-time problem, not a confidence threshold

The brief asks the agent to decide "when there is enough information to act." The naive version of this is
"keep pulling evidence until confidence exceeds N%." That ignores that every additional piece of evidence has
a *cost*: customer friction (a step-up auth prompt), elapsed time (an analyst request might sit for hours
while a compromised card keeps getting used), and opportunity cost (the account may be actively being drained
right now). This is structurally a sequential-decision / stopping-rule problem — closer to Wald's sequential
probability ratio test than to a static classifier threshold. The economically right behavior sometimes isn't
"wait for more certainty," it's "take a cheap, reversible action immediately (temporary hold, step-up auth)
while continuing to gather evidence in parallel," reserving "wait for more certainty" for expensive,
hard-to-reverse actions (permanently closing an account, filing a report, denying a legitimate transaction).
Treating all evidence-gathering as free, and all actions as equally reversible, is the most consequential
modeling mistake available here.

## 8. GraphRAG retrieval can confuse "textually similar" with "causally related"

Retrieving "similar past cases" by embedding similarity over case narratives will happily surface a case that
reads similarly (same merchant category, similar dollar amount) but has a completely different underlying
mechanism, while missing a structurally identical ring that happens to be described in different words. Graph
structural similarity (shared devices, shared accounts, shared IPs, shared ring membership) is a much stronger
relevance signal than text embedding cosine similarity for *this* domain, and the two should be combined with
structure weighted higher — with the system able to say *which* shared entities or signals justify calling two
cases similar, not just that a vector search returned them.

## 9. Perfect escalation defeats the point of building this at all

The stated business problem is that fraud analysts are overloaded. If the agent's answer to uncertainty is
always "escalate to a human," analysts stay exactly as overloaded as before — the system has just added a
routing layer. There needs to be a feedback signal: when a human overrides or agrees with a recommendation,
that outcome should feed back into recalibrating how readily the agent escalates, so the escalation rate
trends toward "only the genuinely hard cases" over time rather than staying flat. Without this closed loop,
"use prior case outcomes ... to inform recommendations" is satisfied only in the shallow sense of retrieval,
never in the sense of the system's own judgment actually improving.

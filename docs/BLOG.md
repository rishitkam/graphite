# The fraud that looked normal: building an agentic investigator on TigerGraph

*Graphite, for the TigerGraph Agentic Fraud Investigation challenge (HHGOA)*

> Every number here was measured; the held-out table comes from one run on frozen code.

## What we built

Graphite takes a fraud alert, investigates it through a TigerGraph graph of
590,742 card transactions, decides what the bank should do under its fraud
policy, and knows when it needs more evidence before acting. Every finished
case is written back into the graph, where the next investigation can find
it.

The challenge asked for three pipelines on the same model (plain RAG,
GraphRAG, Agentic GraphRAG) and judged the improvement between them, not the
absolute score. That turned out to shape almost every decision, because the
first thing we learned is how easy it is to make that comparison lie.

## The evaluation traps

The 20 exam cases come with no answer key. The bank's 5,565 closed cases do
have outcomes, so we held out a slice of them as a labeled test set. Then we
checked what a pipeline could get without investigating anything:

- **The trigger gave the answer away.** Every confirmed fraud in the closed
  cases was opened by a customer report; every false alarm by the bank's
  model. That's a 100 percent split. Eval alerts use a neutral trigger.
- **So did the risk score.** The bank only investigated a legitimate
  transaction when its model scored it high, so on a balanced set "high score
  means cleared" scores 91 percent. We rebuilt the set so every cleared case
  is paired with a fraud case at the same score, within 0.01. A score-only
  rule now gets exactly 50 percent.
- **So did the timing.** Fraud cases were opened a median of 22 hours after
  the transaction, false alarms within about five. Every eval case is
  investigated six hours after its flagged transaction, which is also the
  window every one of the 20 exam cases has.
- **And so would we, if we weren't careful.** Halfway through we caught
  ourselves diagnosing failures on eval cases. We split off a separate dev
  set, and the eval runs once, on frozen code.

None of this is glamorous, but a relative-improvement number is only worth
something if the baseline wasn't handed the answer.

## The data is counterintuitive

With the score neutralised, the evidence runs backwards from fraud-textbook
intuition. False alarms look alarming: online, from a device the account has
never seen. The closed-case notes say why: "cardholder confirmed the purchase
from a new phone." Real fraud often looks mundane: in person, on a card with a
long history.

A model reasoning from general knowledge gets that backwards. Plain RAG on
the dev split scored 42.5 percent, with an AUC of 0.30, well below a coin
flip. It kept flagging new phones and waving through fraud.

## How TigerGraph fixes it

**Graph traversal for the evidence.** Six installed GSQL queries build the
evidence: the card's baseline before the alert, its last 72 hours, who else
used the device, the customer's cards and history, and closed cases that
share structure with the alert. Every query takes an as-of time and an
exclusion set, so neither the future nor a held-out case can leak in.

**Rates, not counts.** An early version reported "5 confirmed fraud cases on
this device" for a profile that turned out to be every iPhone of one
generation, used by 125 customers. That's below the bank's base rate. The
evidence now reports rates beside the base rate, and precedent links are
weighted by one over the square root of how many customers share them.

**Case memory in TigerGraph's vector index.** Every closed case carries two
vectors: its narrative, embedded, and a 15-feature description of what the
graph looked like at alert time (channel, device novelty and proxy, how many
customers share the device, region and product familiarity, amount against
history, velocity). On dev, just asking how the 15 most similar past
situations ended scores 80 percent with an AUC of 0.82, with no language
model at all. The policy and pattern text sits in a third index, so the
agent can cite the rule it's applying.

**Finding the pattern nobody documented.** Exam case HHG-014 is an analyst
request about "the same unusual device profile" on several cards. The
flagged transaction's risk score was 0.05. One hop in the graph: that device
was used 26 times in 30 days, every time new to the account and behind an
anonymous proxy, across 20 different customers, with four confirmed fraud
cases already on it. The agent calls it an undocumented coordinated pattern,
links all 19 other cards, and routes the block and the regulatory report to
humans.

Then we went looking without an alert. A GSQL sweep over November and
December for device profiles that behave like that finds the same ring still
running, now across 28 customers. 27 of them never raised an alert.

## The agentic part

The agent starts lean, with the alert, the flagged transaction and the card's
baseline, about 300 tokens, and chooses what to look at. It has the same
graph tools GraphRAG uses, rendered identically, plus the freedom to follow
leads, search precedent with its own query, and pull policy text. Before
concluding it has to name the most likely innocent explanation and check
it.

It never touches an action. It proposes an assessment; a deterministic
policy engine implementing rules R1 to R10, with tests against the rule
text, turns that into actions and approval routes. All three tiers share
that engine, and the same prompt, and the same output format, so the only
differences between them are retrieval and agency.

## Results

| | Graph memory only (no LLM) | RAG | GraphRAG | Agentic GraphRAG |
|---|---|---|---|---|
| accuracy | 85.7% | 44.0% | 73.8% | **75.6%** |
| AUC | 0.919 | 0.433 | 0.805 | **0.852** |
| Brier (lower is better) | 0.109 | 0.341 | 0.179 | **0.158** |
| fraud recall | 81.8% | 15.9% | 77.3% | 76.1% |
| legit specificity | 90.0% | 75.0% | 70.0% | 75.0% |
| fraud pattern named correctly | n/a | 8.0% | 44.3% | **51.1%** |
| tokens / case | 0 | 1,296 | 2,679 | 4,818 |
| LLM calls / case | 0 | 1.0 | 1.0 | 2.6 |

168 held-out cases (160 score-matched, 80 fraud and 80 cleared, plus 8 rare
patterns), `openai/gpt-oss-120b` on Groq for every tier, run once on frozen
code. GraphRAG beats RAG by 29.8 points (68 percent relative); the agent beats
RAG by 31.5 points (72 percent relative) and beats GraphRAG on ranking,
calibration and naming the pattern.

RAG lands below chance on purpose: once risk scores are matched, notes that
read alike are not situations that are alike. The memory-only row, graph
retrieval with no model at all, is the strongest single number. We keep it
in the table because it is the point: the signal lives in the graph, and the
model's job is to explain it, name the pattern and propose the action.

Exam: 20 cases answered by the agent, 10 fraud, 9 legitimate, 1 uncertain,
every file validated against the answer schema. Proactive: 5 ring cases
found by the graph with no alert, 3 judged fraud with SARs.

## What we learned

- The hardest part of a relative comparison is the baseline. Most of our
  best work went into making sure the weakest pipeline wasn't secretly handed
  the answer.
- A graph is only as good as the questions you ask of it. Raw counts made a
  popular phone look like a fraud ring. Rates against a base rate fixed it.
- Retrieval isn't the same as trust. GraphRAG saw situation memory say 12 of
  15 similar alerts were fraud and went with its gut anyway, until told to
  anchor on the base rate and move only for specific evidence.
- Free-tier rate limits are an architecture constraint, not a nuisance. They
  pushed us to a lean-start agent and compact evidence lines instead of raw
  query dumps.

## What we'd do with more time

- Fit the situation features rather than hand-pick them, and compare against
  a learned model trained only on the memory pool.
- Run the agent on the full eval with and without each tool, to measure what
  each one is worth.
- Replace the simulated customer replies with a small simulator conditioned
  on the case's actual history.
- Stream new transactions into the graph and run the ring sweep continuously
  instead of over a fixed window.

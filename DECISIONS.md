# Decisions

Running log of the calls made on this project and the reasoning behind them.
New entries go at the bottom.

## Read the brief twice, independently, before designing anything
Went through the hackathon brief once purely as a judge, asking what the
rubric actually rewards. Then went through it again from scratch, without
looking back at the first pass, as an engineer trying to find where the
design would break in the real world. Kept the two write ups separate, then
compared them at the end.

Reasoning: optimizing only for the rubric tends to produce something that
scores fine but is fragile underneath. Optimizing only for robustness tends
to skip over concrete, cheap to satisfy requirements that are easy to miss
on a skim, like the submission format quietly wanting two recommendations
per case instead of one. Doing both separately and comparing caught things
that either pass alone would have missed.

## Picked LangGraph for the orchestrator over a role based multi agent setup
The brief's investigation flow is a strict sequence of named steps with one
real loop back in it (gather more evidence, then re-check). That's a state
machine, not a group of agents debating each other. An explicit graph of
states matches the actual shape of the problem, and it makes it easy to pin
the two required recommendation checkpoints to specific nodes instead of
digging them out of a transcript afterward.

## Separated proposing an action from executing one
The orchestrator can read anything on the graph and suggest anything as a
next step, but it can't call an action tool directly. Only a separate,
deterministic policy engine, one that reads structured fields and never
reads model output, can issue the approval ticket that unlocks an action
executor.

Two unrelated reasons landed on the same answer here, which is what made it
feel like the right call rather than just a nice idea. First, the brief
says only authorized actions may be executed and some need human approval,
so this is graded, not optional. Second, if the model is ever handed
something like a merchant name or memo field that a fraudster controls, and
that same model can also call block_account or approve_refund, that's a
real prompt injection path. Splitting propose from execute closes it off
completely instead of hoping the model doesn't fall for it.

## Built fraud pattern detection on graph structure, not just the five documented typologies
The brief says plainly that not every fraud pattern in the data is
documented. A system that only matches against the five known typologies
will fail visibly on whatever isn't one of those five, and the benchmark
cases almost certainly include something outside that list on purpose. So
detection leans on structure instead: shared devices, shared emails, shared
IPs between accounts, community detection to surface rings, and a risk
score propagated outward from accounts that were part of confirmed fraud
cases before. The five typologies still matter, they're just a floor, not
the whole detector.

## Priced evidence gathering instead of using a flat confidence threshold
The obvious approach to "is there enough evidence to act" is to keep
gathering until confidence crosses some number. That treats every extra
fact as free, which it isn't. A step up authentication prompt spends a
customer's patience, an analyst request spends their afternoon, and a card
that's actively being drained spends real money the longer it waits.

So each candidate next piece of evidence gets weighed against what it would
likely resolve versus the cost of the delay it introduces. Something cheap
and reversible, like a temporary hold, gets taken right away while more
evidence keeps coming in. Something expensive and irreversible, like
closing an account or filing a report, still waits for a higher bar. This
also turns out to be what produces the two recommendation checkpoints the
submission format asks for. The first one is just the moment this rule
first fires, before evidence gets requested, and the second is after it
comes back.

## Chose Python, LangGraph, pyTigerGraph, and the TigerGraph MCP server as the stack
Mostly locked in by the brief itself, which requires GSQL, graph
algorithms, and TigerGraph MCP specifically, and pyTigerGraph is the
natural Python client for that. Confirmed it was still the right call
before actually starting to build instead of assuming.

## Dataset link was hidden in the PDF, not in the visible text
The brief names "the dataset" with what looked like a broken icon in the
extracted text, no visible URL. Pulled the actual link annotations out of
the PDF directly and found a Google Drive folder behind it: case_pack.csv,
closed_cases_history.csv, identity.csv, README.md, and transactions.csv at
675 MB. Confirmed the folder is public and has the right files by opening
it, but haven't downloaded anything yet, that's worth a go ahead first
given the size.

## Defaulting to TigerGraph Savanna over Community Edition
Not fully settled yet. Savanna is free for the hackathon, cloud hosted, and
listed first in the brief, so it's the default for now unless there's a
reason to run Community Edition locally instead (offline work, wanting
more control over the instance). Easy to switch early on since nothing has
been built against it yet.

## The dataset's own README replaces most of the earlier guesswork
The hackathon brief alone didn't say what the exact action names were, what
the approval routing looked like, or what fields an answer file needed. The
dataset's README turned out to have all of that spelled out: fourteen named
actions, three approval routes, ten numbered policy rules, exact stopping
thresholds, and the full JSON schema for what gets submitted per case.

This doesn't change the architecture from the design phase, the propose
versus execute split, the cost aware stopping logic, the structural
detection underneath the five patterns all still hold. What it does is
replace the parts that were reasonable guesses with the actual literal
spec. The stopping rule in particular is now a concrete pair of numbers
(fraud probability at or above 0.85, or at or below 0.15, backed by two
independent pieces of evidence) rather than an abstract cost function.
The cost of waiting reasoning from the design phase still matters, it's
what decides which cheap action to take while evidence is still coming in,
it just isn't what decides when to stop anymore. The policy already
decides that.

## Left the 377 opaque Vesta columns out of the graph schema
Transaction has amount, timestamp, product code, channel, risk score,
billing region, and distance fields as real attributes. It does not have
the fourteen C columns, fifteen D columns, nine M columns, or three
hundred thirty nine V columns. The dataset README describes all four
groups the same way: real model features, no names given, usable as
signals. There's no reason to treat any one group as more graph worthy
than another, and no reason to put three hundred seventy seven mostly
opaque numeric attributes on every transaction vertex when none of them
support traversal or relationship reasoning, which is the actual point of
using a graph here instead of a table. They stay in transactions.csv,
readable by txn_id whenever the agent wants to look at raw feature values
for a specific transaction.

## Named the case vertex FraudCase, not Case
CASE is a reserved word in GSQL's own expression syntax. Naming a vertex
type Case would have worked until the day it didn't, in whatever query
first tried to use a CASE WHEN expression near it. FraudCase costs nothing
and avoids that entirely.

## Wrote the schema now, holding the loading jobs until there's a live instance
The schema is just type declarations, low risk to get right without a
running database to check it against. The loading jobs are a different
story: composite device keys built from four concatenated fields, date
parsing, pipe separated lists that need to become multiple edges. Writing
that blind, with no GSQL console to throw an error back, is a good way to
produce something that looks plausible and takes several rounds to
actually get working. Better to write it once against real feedback than
guess at the syntax three times.

## Real transaction IDs are bare numbers, not the README example's style
The dataset README's own worked example uses IDs like T0412877, and a case
ID, HHG-017, that doesn't exist in the real twenty. That example is
illustrative only. The actual transactions.csv has plain numeric IDs like
3514030. Since made up IDs score zero on the actual submission, this is
worth being explicit about now rather than finding out after the agent's
already writing answer files: never invent an ID format, always use
exactly what's in the CSV.

## Restructured as three comparable pipelines instead of one
Got word from the organizers that grading actually compares three tiers
built on the same model: plain RAG, GraphRAG, and Agentic GraphRAG, judged
on the relative improvement between them plus architecture and token
efficiency, not on absolute accuracy alone. That changes what gets built.

Defined the three tiers for this specific task, since none of those words
mean anything concrete on their own:

- RAG: flat vector search over closed case narratives, no graph traversal,
  one LLM call per case.
- GraphRAG: same graph, but retrieval actually walks it, connected device,
  region, shared entities, structurally similar closed cases. Still a
  fixed retrieval pattern decided by the pipeline, not the model, still
  basically one informed call.
- Agentic GraphRAG: what was already being built. The model decides what
  to query, gathers evidence across steps, runs the stopping check, can
  ask for more evidence, hits the policy engine for actions.

Principle going in: the RAG and GraphRAG tiers get genuinely competent
implementations, not strawmen. Sandbagging a baseline to inflate the
improvement number would make the whole comparison meaningless the moment
anyone looked closely, and defeats the actual point being tested.

## Built the accuracy comparison on held out closed cases, not the exam set
The 20 exam cases have no visible answer key, so accuracy can't be
measured on them directly. closed_cases_history.csv does have real
outcomes though, confirmed_fraud or cleared. Plan is to hold out a
stratified slice of it, roughly 80 confirmed fraud and 80 cleared, as an
actual labeled benchmark for the three pipelines, kept separate from the
20 required answer files.

Two things matter for this to be honest. First, balance: the closed cases
are 84 percent confirmed fraud, since they're a pre-filtered
"worth investigating" sample, not the real rate, and evaluating on that
mix would let a pipeline that always guesses fraud score 84 percent doing
nothing. Second, no leakage: whatever's held out for evaluation gets
removed from the retrievable memory pool for that run, so a pipeline
can't score well by literally retrieving the case it's being tested on.

## Standardizing on Claude Haiku 4.5 across all three pipelines
Has to be the same model across all three for the comparison to mean
anything, that part isn't optional. Picked Haiku over Sonnet mainly on
volume, three pipelines times a large eval set times however many calls
the agentic tier makes per case adds up, but also because the organizers
said directly that a cheaper model with a better architecture should be
able to beat an expensive model with a lazy pipeline. Using Haiku for
everything makes that argument instead of just asserting it. Same model
carries through to the actual 20 case submission too, no swapping to
something bigger for the real thing.

## Running TigerGraph Community Edition locally in Docker, not Savanna
Savanna needed an account signup that only the repo owner could do, and
that was sitting as a blocker for several rounds. Docker was already
installed on this machine, so Community Edition 4.2.5 runs locally from
docker-compose.yml instead. No account, no waiting, and the whole setup
is reproducible from the repo. If a hosted instance matters later for the
demo, the schema and loader scripts point at any host through .env.

## Card IDs are derived, not given
transactions.csv has customer_id but no card_id, while every case refers
to cards like C12382-K1. Tested three rules for assigning the K number
against every transaction the closed cases pair with a card. Card type
(card6) sorted alphabetically within a customer matched 14,955 out of
14,955. Order of first use and most used card both came in around 34
percent. Then checked the winning rule against all 20 exam cases, which
it was never fit on, and it matched all 20. Guessing here would have
quietly broken every card level query in all three pipelines.

## Device profiles require an actual device model
The first version of the device key happily built profiles out of just a
browser version. The most "shared" device in the data was Windows 10,
Chrome 63, 1920x1080, used by 842 different customers. That's a popular
laptop, not a fraud ring. A profile now only exists when DeviceInfo is
present, and each transaction's device edge carries whether the device
was New or Found for that account and whether it went through a proxy,
since those are what actually separate a ring from a common setup.

## The eval set is score matched, because the unmatched one was broken
First version of the holdout was just balanced, 80 fraud and 80 cleared.
Then checked the risk score: cleared cases averaged 0.88, fraud averaged
0.46. The bank only opened a case on a legitimate transaction when the
model flagged it, while fraud got opened by customer reports at any
score. A rule as dumb as "high score means cleared" scored 91 percent on
that set. Every tier with retrieval would have learned it from the closed
case notes, which literally say "model scored $X at 0.91, cleared," and
the comparison would have measured nothing.

Rebuilt it so each cleared case is paired with a confirmed fraud case at
nearly the same score (within 0.01). The two sides now have identical
score distributions and the best score-only rule gets exactly 50
percent. Whatever each tier scores now comes from evidence it actually
found. Card testing and undocumented cases are too rare to match on
score, so they sit in a separate small slice graded only on whether the
pattern gets named.

## Eval alerts don't carry the original trigger
Same problem, different field. In the closed cases every confirmed fraud
was opened by a customer report and every cleared case by a model score,
a perfect 100 percent split both ways. Eval alerts use a neutral trigger
with just the transaction, card, amount, and score, so the trigger type
can't give the answer away.

## All three tiers share one policy engine
The policy is implemented once, as a plain function of a structured
assessment (probability, exposure, evidence count, reply, shared origin,
and so on), with tests against the rule text and the README's own worked
example. Every tier produces an assessment and hands it to the same
engine. If each tier wrote its own action logic, a better next best action
score could come from better rule writing instead of better evidence,
and the comparison couldn't tell those apart.

## Load over REST instead of TigerGraph's file loader
The first load through the built in file loader hung with no loader
process running, and on every restart RESTPP tried to resume that dead
job and stopped answering anything else. Aborting it needed RESTPP too.
Recreated the instance (it only held the schema) and now post each CSV to
the same loading job over REST from Python, in 50,000 line chunks, with
valid and rejected counts reported per file. Slower to start, but it
can't silently hang and it says exactly what went in.

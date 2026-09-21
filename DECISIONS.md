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

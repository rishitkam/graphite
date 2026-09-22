# Progress

## Where things stand
Design phase is done. Dataset is in hand and read. Schema is drafted. Scope just grew from one pipeline to three, see below. Need a live TigerGraph instance to go further either way.

## The actual deliverable is now three pipelines, not one
Grading compares plain RAG, GraphRAG, and Agentic GraphRAG built on the
same model, scored on relative improvement between them plus architecture
and token efficiency, not absolute accuracy alone. Full reasoning and the
tier definitions are in DECISIONS.md. Short version: same graph, same
model (Claude Haiku 4.5), three retrieval and agency strategies, evaluated
against a held out balanced slice of closed_cases_history.csv since the
real 20 exam cases have no visible answer key. The 20 required answer
files still come from the agentic tier, the other two exist to prove it's
actually earning its complexity, not to duplicate the submission.

## Done so far
- Read through the full HHGOA brief and pulled apart what it's actually asking for, not just the obvious parts.
- Ran two separate passes on the problem before designing anything: one reading the brief like a judge (what actually earns points), one breaking it like an engineer (where this fails once it's real). Wrote both down on their own, then compared them afterward.
- Turned that into a full system design under design/, called Graphite. Core idea: a fraud case is treated like a sketch that darkens as evidence comes in, instead of jumping straight to a yes/no verdict.
- Built an interactive walkthrough of the design (design/graphite-design.html) alongside the written version (design/SYSTEM_DESIGN.md).
- Found the actual dataset link, which was buried in the PDF's link annotations rather than sitting in the visible text.
- Confirmed the stack: Python, LangGraph for the orchestrator, pyTigerGraph plus the TigerGraph MCP server for the graph side.
- Set up the repo itself: git initialized, .gitignore, basic project layout under src/, gsql/, data/, tests/.
- Dataset landed in data/, unzipped, and checked against the README's own numbers: 590,742 transactions, 144,432 identity records, 5,565 closed cases (4,665 confirmed fraud, 900 cleared), 20 exam cases. All of it matches, no surprises.
- Read the dataset's own README in full. It's much more specific than the hackathon brief alone: exact action names, exact approval routing (auto / L1 / L2), ten numbered policy rules, exact stopping thresholds (0.85 / 0.15 with two independent pieces of evidence), and the full JSON answer format field by field. This isn't guesswork anymore, it's a spec.
- Drafted the graph schema (gsql/01_schema.gsql) starting from the schema the dataset README itself suggests, extended with the live case, evidence, and action vertices the agent needs to write. Not run against a live instance yet, so it's a first draft, not verified.

## Next
- Stand up a TigerGraph instance. Still defaulting to Savanna, still an open call, still needs an account which only the owner of this repo can create. This blocks all three pipelines now, not just one.
- Load the schema, fix whatever GSQL syntax it gets wrong on the first try, then write the actual loading jobs against real error messages instead of guessing at LOAD statement syntax blind.
- Build the NEXT edge (sequential transactions per card) and the ring detection pass (shared device / region / email) as post load queries.
- Build the held out evaluation split from closed_cases_history.csv before building any pipeline, so nothing accidentally gets tuned against it later.
- Then the three pipelines: RAG first since it's the simplest and proves the harness works end to end, then GraphRAG, then the full agentic system with the LangGraph orchestrator, MCP tool wiring, and the ten numbered policy rules implemented literally.
- Get one dumb version running end to end before polishing any single tier. Nothing has executed once yet and that's the actual risk right now, not lack of ideas.

## Watch for
- The closed case history is 84 percent confirmed fraud. That's not the real fraud rate, it's just what gets escalated to a full investigation. The 20 exam cases are roughly half legitimate per the README. Don't let anything calibrate off the closed case mix.
- The dataset README's own worked example uses invented transaction IDs like `T0412877`. The real data's IDs are bare numbers like `3514030`. Made up IDs score zero, so nothing should ever follow the example's ID style, only the real one.
- `TransactionID`, `card1`, `TransactionDT`, and `TransactionAmt` were deliberately altered so the public Kaggle IEEE-CIS files can't be used to look up real outcomes. Don't go near the original public dataset for this project, that's a disqualification, not a shortcut.

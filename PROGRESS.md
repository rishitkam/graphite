# Progress

## Where things stand
Design phase is done. Build phase is starting now.

## Done so far
- Read through the full HHGOA brief and pulled apart what it's actually asking for, not just the obvious parts.
- Ran two separate passes on the problem before designing anything: one reading the brief like a judge (what actually earns points), one breaking it like an engineer (where this fails once it's real). Wrote both down on their own, then compared them afterward.
- Turned that into a full system design under design/, called Graphite. Core idea: a fraud case is treated like a sketch that darkens as evidence comes in, instead of jumping straight to a yes/no verdict.
- Built an interactive walkthrough of the design (design/graphite-design.html) alongside the written version (design/SYSTEM_DESIGN.md).
- Found the actual dataset link, which was buried in the PDF's link annotations rather than sitting in the visible text. It's a Google Drive folder: case_pack.csv, closed_cases_history.csv, identity.csv, README.md, and transactions.csv (675 MB, the big one). Nothing downloaded yet, waiting on a go ahead since that's a lot of data to pull down.
- Confirmed the stack: Python, LangGraph for the orchestrator, pyTigerGraph plus the TigerGraph MCP server for the graph side.
- Set up the repo itself: git initialized, .gitignore, basic project layout under src/, gsql/, data/, tests/.

## Next
- Get the dataset files, starting with the README since the brief says to read that first, before writing any GSQL against guessed column names.
- Stand up a TigerGraph instance. Defaulting to Savanna since the brief lists it first and it's free with nothing to host locally, but that's still an open call.
- Write the actual schema once the real columns and case format are in hand.
- Loader, then GSQL queries, then the agent itself.

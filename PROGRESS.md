# Progress

## Where things stand
Everything is built and running end to end. What's left is compute: the
held-out comparison and the 20 exam answer files need model tokens, and the
Groq free tier allows 200,000 a day. Upgrading to the pay-as-you-go
developer tier would finish it in hours instead of days.

## Built
- **Graph.** TigerGraph Community Edition 4.2.5 in Docker. 2.4 million
  vertices and edges, every count checked against the source files.
  `scripts/rebuild_graph.sh` rebuilds all of it from scratch.
- **Investigation queries.** Six GSQL queries (card window, card baseline,
  device neighbours, customer overview, structural precedent, transaction
  detail), all as of an investigation time with an exclusion set.
- **Vector search in TigerGraph.** Three indexes: closed case narratives,
  closed case situation vectors (case memory), policy and pattern text.
- **Graph algorithms.** The library's weakly connected components over a
  projected customer graph finds fraud rings, including ones that rotate
  across several devices.
- **Three pipelines** on one model (gpt-oss-120b on Groq), sharing one prompt,
  one output format and one policy engine: RAG, GraphRAG, Agentic GraphRAG.
- **Policy engine** implementing R1 to R10, tested against the rule text.
- **Case memory writes.** Every exam case becomes a FraudCase vertex linked to
  its transactions, cards, devices, precedent, evidence and actions.
- **SAR narratives,** only when a report is filed, with facts from the data.
- **Proactive monitoring.** In November and December the ring detection finds
  six rings, 61 customers; five of them, 28 customers, contain none of the
  exam cases.
- **Interface.** Case board, each investigation drawn as a graph, the
  pencil-draft to inked-verdict action change, a proactive rings view, and a
  scoreboard comparing tiers.
- **Evaluation.** A score-matched held-out set, a separate dev split, and tests
  that prove nothing after the investigation time can leak in.
- **Docs.** README, blog post draft and demo script in `docs/`, every decision
  in DECISIONS.md.

## Measured so far (dev split, small samples, direction only)
- Plain RAG: 33 to 42 percent accuracy, AUC 0.30 to 0.39. Below chance: it
  reads new-phone purchases as fraud.
- Graph case memory alone, no model: 77.5 percent, AUC 0.85 on all 40 dev
  cases, after correcting for what the bank chose to investigate.
- GraphRAG and the agent: being rerun on dev after the memory correction.

## Next
1. Finish the 16-case dev comparison for GraphRAG and the agent.
2. Run the agent on the 20 exam cases, export `cases/`, validate every file.
3. Run the proactive monitor for `cases_proactive/`.
4. Freeze the code and run the held-out eval once for all three tiers.
5. Fill the final numbers into the README, blog post and scoreboard.

## Watch for
- Case memory reflects what the bank chose to investigate. Always read it
  against its own base rate, never as a raw fraud share.
- Customer disputes need the recurring charge check (R7): memory has no
  legitimate disputes to learn from.
- The README's worked example uses invented transaction IDs. Real IDs are bare
  numbers, and `scripts/export_cases.py` rejects any ID not in the dataset.
- Never use the public Kaggle IEEE-CIS files. That's disqualification.

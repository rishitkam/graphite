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

## Done
- Exam: 20 answers in `cases/`, all validated, written to the graph with SARs.
- Proactive: 5 ring cases in `cases_proactive/`, 3 fraud with SARs.
- Dev comparison (40 cases) and held-out eval (168 cases), same model.

## Held-out results
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

Full tables in `eval/RESULTS.md`.

## Next
1. Demo video, blog post and social post.
2. Publish the static demo site (needs a yes first).
3. Rotate the Groq keys after judging.

## Watch for
- Case memory reflects what the bank chose to investigate. Always read it
  against its own base rate, never as a raw fraud share.
- Customer disputes need the recurring charge check (R7): memory has no
  legitimate disputes to learn from.
- The README's worked example uses invented transaction IDs. Real IDs are bare
  numbers, and `scripts/export_cases.py` rejects any ID not in the dataset.
- Never use the public Kaggle IEEE-CIS files. That's disqualification.

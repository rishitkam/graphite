| metric | Graph memory only (no LLM) | RAG | GraphRAG | Agentic GraphRAG |
|---|---|---|---|---|
| cases | 40 | 40 | 40 | 40 |
| accuracy | 80.0% | 40.0% | 67.5% | 62.5% |
| AUC | 0.843 | 0.364 | 0.718 | 0.733 |
| Brier (lower is better) | 0.146 | 0.358 | 0.213 | 0.212 |
| fraud recall | 75.0% | 20.0% | 75.0% | 55.0% |
| legit specificity | 85.0% | 60.0% | 60.0% | 70.0% |
| pattern accuracy (fraud) | 0.0% | 15.0% | 25.0% | 25.0% |
| tokens / case | 0.000 | 1,347 | 2,597 | 5,054 |
| LLM calls / case | 0.000 | 1.000 | 1.000 | 2.675 |
| graph+retrieval calls / case | 1.000 | 1.000 | 9.000 | 3.675 |
| seconds / case | 0.000 | 9.015 | 17 | 22 |

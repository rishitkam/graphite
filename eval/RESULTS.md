| metric | Graph memory only (no LLM) | RAG | GraphRAG | Agentic GraphRAG |
|---|---|---|---|---|
| cases | 168 | 168 | 168 | 168 |
| accuracy | 85.7% | 44.0% | 73.8% | 75.6% |
| AUC | 0.919 | 0.433 | 0.805 | 0.852 |
| Brier (lower is better) | 0.109 | 0.341 | 0.179 | 0.158 |
| fraud recall | 81.8% | 15.9% | 77.3% | 76.1% |
| legit specificity | 90.0% | 75.0% | 70.0% | 75.0% |
| pattern accuracy (fraud) | 0.0% | 8.0% | 44.3% | 51.1% |
| tokens / case | 0.000 | 1,296 | 2,679 | 4,818 |
| LLM calls / case | 0.000 | 1.000 | 1.000 | 2.554 |
| graph+retrieval calls / case | 1.000 | 1.000 | 9.000 | 3.554 |
| seconds / case | 0.000 | 7.160 | 16 | 24 |

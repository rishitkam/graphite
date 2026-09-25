# Social post

Ready to paste. Trim for X if needed; a shorter version is below.

---

Just wrapped the TigerGraph Agentic Fraud Investigation challenge with
@TigerGraphDB and @247pmstudio, and it taught me more about evaluation than
about AI.

The task: take 20 fraud alerts, investigate each one through a graph of
590k card transactions, and compare three pipelines on the same model:
plain RAG, GraphRAG, and an agent that picks its own graph queries.

What I built, Graphite:
- All three pipelines share one prompt, one output format and one policy
  engine. Only retrieval changes, so the comparison actually means something.
- The model proposes a verdict. Ten written policy rules decide whether a
  card gets blocked or a report gets filed. The model never acts on its own.
- Every graph query runs through TigerGraph's official MCP server.
- It finds fraud rings nobody reported: customers linked by devices that
  were new to all of them, grouped with TigerGraph's connected components.

The part I didn't expect: the first honest test is the hard one. In the
bank's history the alert type predicted the outcome perfectly and the risk
score got 91 percent on its own. So I built a test set where fraud and
cleared cases have the same risk score, froze the code, and ran it once.

Results on 168 held-out cases, same model (gpt-oss-120b) everywhere:
RAG 44%, GraphRAG 73.8%, agent 75.6%. AUC 0.43, 0.81, 0.85.

RAG came in below a coin flip, and that's the lesson: notes that read alike
are not situations that are alike. The graph is what knows the difference.

Favourite bug: a customer disputed a $49 charge, and the agent called it
fraud. The card had 53 earlier $49 charges. It was their subscription. The
agent had been told to check for that and skipped it, so now the pipeline
runs that check itself. Policy shouldn't be optional.

Everything is open, including every raw answer and every decision I made
along the way: github.com/rishitkam/graphite

#TigerGraph #GraphRAG #AIAgents #FraudDetection

---

## Short version (X)

Built Graphite for the @TigerGraphDB x @247pmstudio fraud challenge: an
agent that investigates card fraud through a graph.

Same model, three pipelines, a test set built so the risk score can't do
the work:
RAG 44% / GraphRAG 73.8% / agent 75.6%

Notes that read alike aren't cases that are alike. The graph knows.

github.com/rishitkam/graphite

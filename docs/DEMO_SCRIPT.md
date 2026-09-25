# Demo script, about 4 minutes

Screen: the Graphite interface (`uvicorn graphite.ui.app:app --port 8765`),
with TigerGraph running in Docker. Every case named here is in the repo.

**0:00 to 0:25, the problem.** "Fraud teams get more alerts than they can
investigate, and many are false alarms. Graphite investigates each alert
through a TigerGraph graph of 590 thousand transactions, proposes a verdict,
and a fixed policy engine decides what the bank does."

**0:25 to 1:05, how it's built.** One slide or the README diagram.
- Three pipelines, RAG, GraphRAG and an agent, on one model (gpt-oss-120b).
  Same prompt, same output, same policy rules. Only retrieval changes.
- Every graph query goes through TigerGraph's official MCP server.
- The model proposes; rules R1 to R10 decide. The model never blocks a card.

**1:05 to 1:50, the scoreboard.** Switch to the Scoreboard, held-out set.
- "First we made the test hard to game. In the bank's history the risk score
  alone gets 91 percent, so our 160 test cases are matched on it: fraud and
  cleared cases with the same score."
- Read the row: RAG 44, GraphRAG 73.8, agent 75.6 percent. AUC 0.43, 0.81,
  0.85. "Same model. The graph is the difference."
- "The agent spends more tokens, and it spends them on getting the story
  right: it names the fraud pattern 51 percent of the time, RAG 8."

**1:50 to 2:35, a dispute done right (HHG-003).** Open HHG-003.
- The customer says they never made a $49.00 purchase.
- Show the recurring check: 53 earlier $49.00 charges on the same card.
- Verdict legitimate, nothing blocked, 1,775 tokens, one model call.
- "On the first run the agent skipped this check. Policy isn't optional, so
  now the harness runs it on every dispute before the agent starts."

**2:35 to 3:05, a false alarm (CC-0574 on the eval board).** A cleared
transaction RAG called fraud. Show GraphRAG and the agent clearing it, and
the situation memory line: the most similar past alerts mostly ended cleared,
read against the bank's own 85 percent fraud base rate.

**3:05 to 3:45, fraud nobody reported (PRO-003).** Switch to Proactive.
- "No alert at all. A sweep links customers who share a device that was new
  to each of them, mostly through proxies, and TigerGraph's connected
  components finds the rings."
- PRO-003: 7 customers, 23 device profiles, 8 cards flagged, SAR filed.
- Mention PRO-002 and PRO-005 were cleared: "It doesn't call every ring
  fraud."

**3:45 to 4:05, close.** "Every case is written back into the graph, so the
next investigation that touches these cards finds it. The numbers, every
raw answer and every decision we made are in the repo."

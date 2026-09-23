# Demo script, about 4 minutes

Screen: the Graphite interface (`uvicorn graphite.ui.app:app --port 8765`),
with TigerGraph running in Docker.

**0:00 to 0:30, the problem.** "Fraud teams get alerts faster than they can
investigate them, and most alerts are wrong. Graphite investigates an alert
through a TigerGraph graph of 590 thousand transactions, decides what the
bank should do under its policy, and knows when it needs more evidence."

**0:30 to 1:30, the ring (HHG-014).** Open HHG-014 on the case board.
- Point at the risk score: 0.05. "The bank's model waved this through."
- Point at the graph: the device in the middle, the ring of cards around it.
  "One hop: this device was used 26 times in 30 days, every time new to the
  account, every time behind an anonymous proxy, by 20 different customers."
- Point at the verdict: undocumented pattern, 19 connected cards, the SAR.
- Point at the pencil draft and the inked verdict: "the model proposes; a
  deterministic policy engine decides the actions and who has to approve
  them. Blocking goes to a team lead, the regulatory report to a fraud
  manager."
- Point at the trace: which tools the agent chose, and what it cost in
  tokens.

**1:30 to 2:30, the comparison.** Switch to the Scoreboard.
- "We had to compare plain RAG, GraphRAG and an agent on the same model.
  First we made sure the comparison couldn't be gamed: in the bank's
  history, the trigger alone predicts the outcome perfectly, and the risk
  score gets 91 percent. Our test set is matched so the score gets exactly
  50."
- Read the three accuracies and the improvement. "Plain RAG reads this data
  backwards: new phones look like fraud to it. The graph remembers that most
  alerts like that were cleared."

**2:30 to 3:15, a false alarm done right.** Open a legitimate case where RAG
said fraud and the graph tiers didn't. Show situation memory: "of the 15 most
similar past alerts, most were cleared." Show that nothing got blocked.

**3:15 to 3:50, beyond the 20 cases.** Open `cases_proactive/`. "With no alert
at all, a GSQL sweep over November and December found the same ring still
running across 28 customers. 27 of them never raised an alert. The agent
investigated the ring once, not 27 times."

**3:50 to 4:10, close.** "Everything is written back into the graph as case
memory. The next investigation that touches any of these cards finds it."

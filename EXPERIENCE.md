# Social post

Built a fraud detective for the @TigerGraphDB x @247pmstudio challenge.

Plot twist: the first suspect it arrested was a guy paying for his own
subscription. 53 times. Same $49. The agent looked right at it and yelled
"FRAUD." We've since had a talk.

Same model, three approaches, a test the risk score couldn't cheat on:
plain RAG 44% (worse than a coin, genuinely impressive),
GraphRAG 73.8%, the agent 75.6%.

Turns out fraud isn't in what people write. It's in who shares a phone
with whom. Graphs know. Graphs always know.

It also finds fraud rings nobody reported, which is either very cool or
very creepy depending on which side of the ring you're on.

github.com/rishitkam/graphite

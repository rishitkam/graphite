"""Split the dataset README's policy and pattern text into citable documents
and load them, embedded, into TigerGraph."""

import re
from pathlib import Path

from graphite.pipelines import rag
from graphite.tg import connect

ROOT = Path(__file__).resolve().parent.parent


def sections(text):
    docs = []
    for m in re.finditer(r"\*\*(\d)\. ([^*]+?)\.\*\* (.+)", text):
        docs.append((f"PATTERN-{m.group(1)}", "Known fraud patterns", m.group(2), m.group(3).strip()))
    for m in re.finditer(r"\*\*(R\d+)\. ([^*]+?)\*\* (.+)", text):
        docs.append((m.group(1), "Fraud Policy 3. Rules", m.group(2).rstrip("."), m.group(3).strip()))
    for heading, doc_id in [("### 3a. A case is not a report", "POLICY-3a"), ("### 3b. The next best action can change", "POLICY-3b"),
                            ("### 4. Exposure", "POLICY-4"), ("### 5. Gathering more evidence", "POLICY-5"),
                            ("### 6. Stopping", "POLICY-6"), ("### 7. Explaining", "POLICY-7"),
                            ("### 2. Approval routing", "POLICY-2"), ("## Things to know", "GUIDANCE")]:
        start = text.index(heading) + len(heading)
        end = text.find("\n#", start)
        body = " ".join(text[start:end].split())
        docs.append((doc_id, "Fraud Policy" if doc_id != "GUIDANCE" else "Dataset guidance", heading.lstrip("# "), body))
    return docs


def main():
    docs = sections((ROOT / "data" / "README.md").read_text())
    conn = connect()
    clean = [(d, s, t, b.replace("|", "/").replace("\n", " ")) for d, s, t, b in docs]
    body = "\n".join("|".join(x) for x in clean) + "\n"
    ok = conn.runLoadingJobWithData(body, "f_doc", "load_documents", sep="|")[0]["statistics"]["parsingStatistics"]["fileLevel"]["validLine"]
    vecs = rag._model().embed([f"{t}. {b}" for _, _, t, b in clean])
    emb = "\n".join(f"{d}|{':'.join(f'{x:.6f}' for x in v)}" for (d, *_), v in zip(clean, vecs)) + "\n"
    okv = conn.runLoadingJobWithData(emb, "f_doc_emb", "load_documents", sep="|")[0]["statistics"]["parsingStatistics"]["fileLevel"]["validLine"]
    print(f"{ok} documents, {okv} embeddings: {', '.join(d for d, *_ in clean)}")


if __name__ == "__main__":
    main()

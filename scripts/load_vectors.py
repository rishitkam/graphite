"""Load both kinds of case memory into TigerGraph's vector index."""

from pathlib import Path

import numpy as np

from graphite import data
from graphite.pipelines import rag
from graphite.tg import connect

ROOT = Path(__file__).resolve().parent.parent


def lines(ids, vecs):
    return "\n".join(f"{i}|{':'.join(f'{x:.6f}' for x in v)}" for i, v in zip(ids, vecs)) + "\n"


def post(conn, var, body, chunk=1000):
    rows = body.splitlines(keepends=True)
    ok = 0
    for i in range(0, len(rows), chunk):
        res = conn.runLoadingJobWithData("".join(rows[i:i + chunk]), var, "load_vectors", sep="|")
        ok += res[0]["statistics"]["parsingStatistics"]["fileLevel"]["validLine"]
    return ok


def main():
    conn = connect()
    cc, notes = rag._index()
    print("note_emb", post(conn, "f_note", lines(cc["case_id"], notes)))
    z = np.load(ROOT / "data" / "situations.npz", allow_pickle=True)
    print("situation", post(conn, "f_situation", lines(z["case_ids"], z["vectors"])))


if __name__ == "__main__":
    main()

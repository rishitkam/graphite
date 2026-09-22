"""Post the prepared CSVs to the load_graphite job over REST, one file at a time.

TigerGraph's local file-loader process hung on the first attempt and took
RESTPP down with it on every restart. Posting through RESTPP skips that
process and reports per-file results.
"""

import sys
import time
from pathlib import Path

from graphite.tg import connect

LOAD = Path(__file__).resolve().parent.parent / "data" / "load"

# Vertices before the edges that reference them.
FILES = [
    ("f_customers", "customers.csv"),
    ("f_cards", "cards.csv"),
    ("f_tx", "transactions.csv"),
    ("f_tx_email", "tx_email.csv"),
    ("f_tx_region", "tx_region.csv"),
    ("f_tx_next", "tx_next.csv"),
    ("f_devices", "devices.csv"),
    ("f_tx_device", "tx_device.csv"),
    ("f_cc", "closed_cases.csv"),
    ("f_cc_involves", "cc_involves.csv"),
    ("f_cc_on_card", "cc_on_card.csv"),
    ("f_cc_connected", "cc_connected.csv"),
]

CHUNK_LINES = 50_000


def chunks(path):
    # Header is dropped here: REST posting doesn't skip it, and the job maps
    # columns by position (see gsql/02_load.gsql).
    with open(path) as f:
        f.readline()
        batch = []
        for line in f:
            batch.append(line)
            if len(batch) == CHUNK_LINES:
                yield "".join(batch)
                batch = []
        if batch:
            yield "".join(batch)


def main():
    conn = connect()
    only = set(sys.argv[1:])
    for var, name in FILES:
        if only and var not in only:
            continue
        start = time.time()
        ok = bad_lines = bad_objects = 0
        for body in chunks(LOAD / name):
            res = conn.runLoadingJobWithData(body, var, "load_graphite", sep=",")
            parsed = res[0]["statistics"]["parsingStatistics"]
            file_level = parsed["fileLevel"]
            ok += file_level.get("validLine", 0)
            bad_lines += sum(v for k, v in file_level.items() if k != "validLine")
            for kind in ("vertex", "edge"):
                for obj in parsed["objectLevel"][kind]:
                    bad_objects += sum(v for k, v in obj.items() if k.startswith("invalid") or k.startswith("no"))
        print(f"{name:<20} valid {ok:>9,}  bad lines {bad_lines:>6,}  bad objects {bad_objects:>6,}  {time.time() - start:6.1f}s", flush=True)


if __name__ == "__main__":
    main()

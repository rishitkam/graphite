"""Find fraud rings with TigerGraph's weakly connected components.

  python scripts/find_rings.py 2016-07-01 2016-10-31   # validate on history
  python scripts/find_rings.py 2016-11-01 2016-12-31   # the exam period

Builds the suspect-device customer links for the window (gsql/09_rings.gsql),
runs the library tg_wcc over them, and reports every component with three or
more customers, checked against the customers the bank confirmed as fraud
victims. The links are cleared first, so windows never mix.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

from graphite import data
from graphite.graph_tools import conn

ROOT = Path(__file__).resolve().parent.parent
# Set on July to October only, before the exam period was looked at.
MAX_CUSTOMERS = 60
MIN_PROXY_SHARE = 0.5
CLEAR = """INTERPRET QUERY () FOR GRAPH Graphite {
  C = {Customer.*};
  X = SELECT c FROM C:c -(SHARES_SUSPECT_DEVICE:e)- Customer:x ACCUM DELETE(e);
}"""


def main(start, end):
    c = conn()
    c.runInterpretedQuery(CLEAR)
    built = c.runInstalledQuery("build_ring_links", {"t_start": f"{start} 00:00:00", "t_end": f"{end} 23:59:59",
                                                     "max_customers": MAX_CUSTOMERS, "min_proxy_share": MIN_PROXY_SHARE})
    wcc = c.runInstalledQuery("tg_wcc", {"v_type_set": ["Customer"], "e_type_set": ["SHARES_SUSPECT_DEVICE"],
                                         "print_limit": -1, "print_results": True})
    members = defaultdict(list)
    for part in wcc:
        for v in part.get("Start", []):
            members[v["attributes"]["Start.@min_cc_id"]].append(v["v_id"])
    rings = sorted((m for m in members.values() if len(m) >= 3), key=len, reverse=True)

    cc = data.closed_cases()
    victims = set(cc[cc.outcome == "confirmed_fraud"].customer_id)
    out = []
    for m in rings:
        confirmed = sorted(set(m) & victims)
        out.append({"customers": sorted(m), "size": len(m), "confirmed_fraud_customers": len(confirmed)})
    print(f"{start} to {end}: {built[0]['links_created']} links over {built[0]['devices_used']} devices, "
          f"{len(rings)} components with 3+ customers")
    for r in out:
        print(f"  size {r['size']:>3}, {r['confirmed_fraud_customers']} with a confirmed fraud case")
    (ROOT / "eval" / f"rings_{start}_{end}.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])

"""Freeze the interface into a static site in site/, for a public demo link.

Calls the same functions the live API serves and writes each response to a
JSON file; site/index.html is the live interface, which reads those files
when it isn't running on localhost. Rerun after new results land.
"""

import json
import shutil
from pathlib import Path

from graphite import alerts
from graphite.ui import app

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
TIERS = ["agentic", "graphrag", "rag"]
SETS = ["exam", "dev", "eval", "proactive"]


def dump(path, obj):
    p = SITE / "data" / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, default=str))


def main():
    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "data").mkdir(parents=True)
    shutil.copy(ROOT / "src" / "graphite" / "ui" / "index.html", SITE / "index.html")
    written = 0
    for which in SETS:
        for tier in TIERS:
            rows = app.cases(tier=tier, which=which)
            dump(f"cases/{tier}/{which}.json", rows)
            for r in rows:
                if r.get("done"):
                    dump(f"case/{tier}/{which}/{r['case_id']}.json", app.case(tier, which, r["case_id"]))
                    dump(f"graph/{tier}/{which}/{r['case_id']}.json", app.graph(tier, which, r["case_id"]))
                    written += 1
    for a in alerts.exam_alerts():
        dump(f"preview/{a.case_id}.json", app.preview(a.case_id))
    for which in ("dev", "eval"):
        dump(f"compare/{which}.json", app.compare(which))
    print(f"site/ written: {written} case views, {len(alerts.exam_alerts())} previews")


if __name__ == "__main__":
    main()

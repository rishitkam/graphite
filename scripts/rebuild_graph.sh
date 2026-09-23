#!/usr/bin/env bash
# Rebuild the Graphite graph from scratch: schema, loading job, data, queries.
# Safe to rerun. Needs the graphite-tg container from docker-compose.yml.
set -euo pipefail
cd "$(dirname "$0")/.."

GSQL="docker exec graphite-tg /home/tigergraph/tigergraph/app/4.2.5/cmd/gsql"

echo "== dropping everything"
$GSQL 'DROP ALL' | tail -1

echo "== schema"
$GSQL /home/tigergraph/gsql/01_schema.gsql | tail -1

echo "== loading job"
$GSQL /home/tigergraph/gsql/02_load.gsql | tail -1

until curl -s -m 5 http://localhost:14240/restpp/echo | grep -q Hello; do sleep 3; done

echo "== data"
[ -f data/load/transactions.csv ] || .venv/bin/python scripts/prepare_load.py
.venv/bin/python scripts/load_graph.py 2>&1 | grep -v Warning

echo "== verify (waits for async ingestion)"
for i in $(seq 1 20); do
  if .venv/bin/python scripts/verify_graph.py >/tmp/graphite_verify.txt 2>/dev/null; then
    cat /tmp/graphite_verify.txt; break
  fi
  sleep 10
done
.venv/bin/python scripts/verify_graph.py >/dev/null 2>&1 || { cat /tmp/graphite_verify.txt; echo "counts do not match"; exit 1; }

echo "== queries"
$GSQL /home/tigergraph/gsql/03_queries.gsql | grep -iE "error|draft|created" || true
$GSQL -g Graphite 'INSTALL QUERY ALL' | tail -3

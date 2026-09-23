#!/usr/bin/env bash
# Run GSQL inside the TigerGraph container. Pass a statement or a path under gsql/.
exec docker exec graphite-tg /home/tigergraph/tigergraph/app/4.2.5/cmd/gsql "$@"

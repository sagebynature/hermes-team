#!/usr/bin/env bash
set -euo pipefail
for agent in atlas vega scout forge lumen blitz ledger sentinel; do
  echo "=== $agent ==="
  docker compose run --rm "$agent" doctor || true
done

#!/usr/bin/env bash
set -euo pipefail

agents=(atlas vega scout forge lumen blitz ledger sentinel)

for agent in "${agents[@]}"; do
  echo "=== $agent ==="
  # The custom image entrypoint bootstraps mounted homes on each run
  # (.local/bin/hermes symlink, Skills Hub lock), so doctor can stay read-only
  # and won't rewrite the committed baseline config.yaml files.
  docker compose run --rm "$agent" doctor
  echo
done

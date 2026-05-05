#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
compose_cmd="${COMPOSE:-docker compose -f docker-compose.yml -f docker-compose.agents.generated.yml -f docker-compose.dashboards.generated.yml}"
read -r -a agents <<< "$(python3 scripts/team_registry.py list-enabled-slugs)"

for agent in "${agents[@]}"; do
  echo "=== $agent ==="
  # The custom image entrypoint bootstraps mounted homes on each run
  # (.local/bin/hermes symlink, Skills Hub lock), so doctor can stay read-only
  # and won't rewrite the committed baseline config.yaml files.
  # shellcheck disable=SC2086
  $compose_cmd run --rm "$agent" doctor
  echo
done

#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <assignee> <task_id>" >&2
}

if [ "$#" -ne 2 ]; then
  usage
  exit 2
fi

assignee="$1"
task_id="$2"
container_name="team-nexus-${assignee}-task-${task_id}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
registry="$repo_root/shared/team-agents.yaml"

if [ ! -f "$registry" ]; then
  echo "Missing agent registry: $registry" >&2
  exit 2
fi

if ! grep -Eq "^  ${assignee}:$" "$registry"; then
  echo "Unknown assignee '$assignee'. Expected one of:" >&2
  grep -E '^  [a-z0-9_-]+:$' "$registry" | sed 's/^  //; s/:$//' >&2
  exit 2
fi

printf '==> Team Nexus Kanban dispatch
'
printf 'assignee: %s
' "$assignee"
printf 'task:     %s
' "$task_id"
printf 'started:  %s
' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cd "$repo_root"
compose_cmd="${COMPOSE:-docker compose -f docker-compose.yml -f docker-compose.agents.generated.yml -f docker-compose.dashboards.generated.yml}"
cleanup() {
  # Best-effort cleanup for dispatcher timeout cancellation.
  docker rm -f "$container_name" >/dev/null 2>&1 || true
}
trap cleanup INT TERM
set +e
# shellcheck disable=SC2086
$compose_cmd run --rm --name "$container_name" "$assignee" chat -q "work kanban task $task_id"
status="$?"
set -e
trap - INT TERM

printf 'finished: %s
' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'exit_code: %s
' "$status"
exit "$status"

#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <assignee> <task_id> [--direct-reply]" >&2
}

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  usage
  exit 2
fi

assignee="$1"
task_id="$2"
direct_reply="0"
if [ "${3:-}" = "--direct-reply" ]; then
  direct_reply="1"
elif [ "$#" -eq 3 ]; then
  usage
  exit 2
fi
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

printf '==> Team Nexus Kanban dispatch\n'
printf 'assignee: %s\n' "$assignee"
printf 'task:     %s\n' "$task_id"
printf 'direct_reply: %s\n' "$direct_reply"
printf 'started:  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cd "$repo_root"
compose_cmd="${COMPOSE:-docker compose -f docker-compose.yml -f docker-compose.agents.generated.yml -f docker-compose.dashboards.generated.yml}"
cleanup() {
  # Best-effort cleanup for dispatcher timeout cancellation.
  docker rm -f "$container_name" >/dev/null 2>&1 || true
}
trap cleanup INT TERM
set +e
if [ "$direct_reply" = "1" ]; then
  # Give public-reply tasks the messaging tool only for this one-off run.
  # Ordinary worker fan-out still runs with the agent's default hermes-cli+kanban toolset.
  # shellcheck disable=SC2086
  $compose_cmd run --rm --name "$container_name" "$assignee" chat -t hermes-cli,kanban,messaging -q "work kanban task $task_id"
else
  # shellcheck disable=SC2086
  $compose_cmd run --rm --name "$container_name" "$assignee" chat -q "work kanban task $task_id"
fi
status="$?"
set -e
trap - INT TERM

printf 'finished: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'exit_code: %s\n' "$status"
exit "$status"

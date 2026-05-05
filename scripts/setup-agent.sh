#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
compose_cmd="${COMPOSE:-docker compose -f docker-compose.yml -f docker-compose.agents.generated.yml -f docker-compose.dashboards.generated.yml}"

usage() {
  echo "usage: scripts/setup-agent.sh <agent>" >&2
  printf 'agents: ' >&2
  python3 scripts/team_registry.py list-enabled-slugs >&2 || true
}

agent="${1:-}"
if [ -z "$agent" ] || ! python3 scripts/team_registry.py list-enabled-slugs | tr ' ' '\n' | grep -Fxq "$agent"; then
  usage
  exit 1
fi

# Avoid invoking Hermes' interactive setup wizard from a non-TTY script. The
# agent homes in this repo carry baseline config.yaml/SOUL.md/AGENTS.md files;
# secrets belong in the repo-root .env loaded by Compose, or the caller's environment.
# `doctor` is intentionally read-only here. The custom image entrypoint performs
# the idempotent bootstrap that fresh mounted homes need without expanding or
# rewriting the committed baseline config.yaml files.
# Ensure shared bind-mount sources exist before Compose can create them as root-owned
# fallback directories. This keeps the artifact handoff submount writable while
# the rest of /shared/project remains read-only inside agent containers.
mkdir -p shared/project/artifacts shared/kanban
if [ ! -f shared/project/artifacts/.gitignore ]; then
  printf '*\n!.gitignore\n' > shared/project/artifacts/.gitignore
fi
chmod 2775 shared/project/artifacts shared/kanban 2>/dev/null || true

# shellcheck disable=SC2086
$compose_cmd run --rm "$agent" doctor

if [ -t 0 ]; then
  echo
  echo "Optional: run gateway setup interactively for $agent now? [y/N] "
  read -r answer
  case "$answer" in
    y|Y|yes|YES)
      # shellcheck disable=SC2086
      $compose_cmd run --rm "$agent" gateway setup
      ;;
  esac
else
  echo "Non-interactive shell detected; skipping optional gateway setup." >&2
  echo "Run 'COMPOSE=\"$compose_cmd\" scripts/setup-agent.sh $agent' from a TTY if needed." >&2
fi

# shellcheck disable=SC2086
$compose_cmd run --rm "$agent" doctor

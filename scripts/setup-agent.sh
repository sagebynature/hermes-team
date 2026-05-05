#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: scripts/setup-agent.sh <agent>" >&2
  echo "agents: atlas vega scout forge lumen blitz ledger sentinel" >&2
}

agent="${1:-}"
case "$agent" in
  atlas|vega|scout|forge|lumen|blitz|ledger|sentinel) ;;
  *) usage; exit 1 ;;
esac

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

docker compose run --rm "$agent" doctor

if [ -t 0 ]; then
  echo
  echo "Optional: run gateway setup interactively for $agent now? [y/N] "
  read -r answer
  case "$answer" in
    y|Y|yes|YES) docker compose run --rm "$agent" gateway setup ;;
  esac
else
  echo "Non-interactive shell detected; skipping optional gateway setup." >&2
  echo "Run 'docker compose run --rm $agent gateway setup' from a TTY if needed." >&2
fi

docker compose run --rm "$agent" doctor

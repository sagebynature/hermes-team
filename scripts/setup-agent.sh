#!/usr/bin/env bash
set -euo pipefail
agent="${1:?usage: scripts/setup-agent.sh <agent>}"
docker compose run --rm "$agent" setup
docker compose run --rm "$agent" gateway setup
docker compose run --rm "$agent" doctor

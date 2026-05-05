#!/usr/bin/env bash
set -euo pipefail

# Team Nexus bootstrap layer.
# Runs before the upstream Hermes Docker entrypoint so mounted agent homes from a
# fresh clone have the small runtime files Hermes doctor expects. Keep this file
# idempotent: it runs on every container start.

HERMES_HOME="${HERMES_HOME:-/opt/data}"
HERMES_KANBAN_HOME="${HERMES_KANBAN_HOME:-}"
HERMES_VENV_BIN="${HERMES_VENV_BIN:-/opt/hermes/.venv/bin/hermes}"

# The upstream Hermes entrypoint can remap the runtime `hermes` user with
# HERMES_UID/HERMES_GID, but Team Nexus creates and chowns shared bind-mounted
# directories before handing off to it. Apply the same remap first so Ubuntu
# hosts keep agent homes, Kanban state, and handoff artifacts owned by the
# operator rather than the image default UID/GID 10000.
if [ "$(id -u)" = "0" ]; then
  if [ -n "${HERMES_GID:-}" ] && [ "$HERMES_GID" != "$(id -g hermes)" ]; then
    groupmod -o -g "$HERMES_GID" hermes 2>/dev/null || true
  fi
  if [ -n "${HERMES_UID:-}" ] && [ "$HERMES_UID" != "$(id -u hermes)" ]; then
    usermod -u "$HERMES_UID" hermes
  fi
fi

if [ -n "$HERMES_HOME" ]; then
  mkdir -p "$HERMES_HOME/.local/bin" "$HERMES_HOME/skills/.hub"

  if [ -x "$HERMES_VENV_BIN" ]; then
    ln -sfn "$HERMES_VENV_BIN" "$HERMES_HOME/.local/bin/hermes"
  fi

  # `hermes skills list` normally initializes this. Creating the minimal lock
  # file here avoids every freshly cloned agent home reporting an uninitialized
  # Skills Hub before any hub skills have been installed.
  if [ ! -f "$HERMES_HOME/skills/.hub/lock.json" ]; then
    printf '{"installed":{}}\n' > "$HERMES_HOME/skills/.hub/lock.json"
  fi

  # Keep the agent-local Hermes shim on PATH and avoid root-only PATH entries
  # after the upstream entrypoint drops privileges to the hermes user. Python's
  # execvp reports PermissionError for missing commands if any PATH directory is
  # not searchable, which made doctor crash while probing optional CLIs like gh.
  export PATH="$HERMES_HOME/.local/bin:${PATH//:\/root\/.local\/bin/}"

  # The upstream entrypoint also fixes ownership, but these paths are created by
  # this wrapper and should be writable after privilege drop.
  chown -hR hermes:hermes "$HERMES_HOME/.local" "$HERMES_HOME/skills/.hub" 2>/dev/null || true
fi

if [ -n "$HERMES_KANBAN_HOME" ]; then
  # Shared writable Kanban root for the whole Team Nexus Compose stack.
  # Hermes initializes the SQLite schema lazily; the entrypoint just ensures
  # the mounted directory exists and remains writable after privilege drop.
  mkdir -p "$HERMES_KANBAN_HOME"
  chown -hR hermes:hermes "$HERMES_KANBAN_HOME" 2>/dev/null || true
fi

TEAM_NEXUS_ARTIFACTS_DIR="${TEAM_NEXUS_ARTIFACTS_DIR:-/shared/project/artifacts}"
if [ -n "$TEAM_NEXUS_ARTIFACTS_DIR" ]; then
  # Cross-agent handoff artifacts are the only writable submount under the
  # otherwise read-only /shared/project tree. If Compose created the bind source
  # on a fresh checkout, normalize ownership before the upstream entrypoint drops
  # privileges.
  mkdir -p "$TEAM_NEXUS_ARTIFACTS_DIR" 2>/dev/null || true
  if [ -d "$TEAM_NEXUS_ARTIFACTS_DIR" ]; then
    chown -hR hermes:hermes "$TEAM_NEXUS_ARTIFACTS_DIR" 2>/dev/null || true
  fi
fi

exec /opt/hermes/docker/entrypoint.sh "$@"

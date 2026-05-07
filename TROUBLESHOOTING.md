# Team Nexus troubleshooting

Use this guide when a profile-driven Team Nexus worker fails to start, a Kanban task is stuck, or runtime state looks inconsistent.

Run commands from the repo root:

```bash
cd /home/sage/team-nexus
```

If your checkout lives somewhere else, use that path instead.

## Fast triage

```bash
make ps
make logs SERVICE=atlas-gateway
make kanban-stats
make kanban-list
make profile-permissions-check
make doctor-all
```

For a specific profile:

```bash
make doctor PROFILE=forge
make shell PROFILE=forge
```

`make shell` is intentionally non-root. Use `make root-shell PROFILE=forge` only when you deliberately need root for runtime ownership repair.

## Kanban task is failing or stuck

Symptoms:

- Task remains `running` or `blocked` after dispatch.
- Atlas reports a dispatcher or worker runtime failure.
- Worker logs show a Python exception, auth lock error, or unknown skill.

Inspect the task and logs:

```bash
make kanban-list
make logs SERVICE=atlas-gateway
```

If you know the board/task log path, inspect the task-specific log under ignored runtime state:

```text
runtime/hermes/kanban/kanban/boards/<board>/logs/<task-id>.log
```

Common examples:

```text
runtime/hermes/kanban/kanban/boards/nj-onnuri/logs/t_6cfd3310.log
```

Do not commit files from `runtime/`; it may contain secrets, auth, sessions, memory, logs, checkpoints, and live Kanban databases.

## `Error: Unknown skill(s): kanban-worker`

What it means:

The Kanban dispatcher starts workers with the built-in worker skill, usually equivalent to:

```text
hermes -p <profile> --skills kanban-worker chat -q ...
```

If the target profile cannot resolve `kanban-worker`, the worker exits before it can perform the task. This commonly happens when the skill exists only in one profile's local runtime skill directory, such as Atlas, instead of the repo-visible shared skill tree.

Check whether the canonical shared skills exist:

```bash
test -f shared/skills/devops/kanban-worker/SKILL.md
test -f shared/skills/devops/kanban-orchestrator/SKILL.md
```

Check which shared skill paths are rendered into profiles:

```bash
make profile-render-docker-dry-run
make profile-render
make doctor-all
```

Durable fix:

- Team-wide worker/orchestrator procedures belong under `shared/skills/`.
- Role-specific skill selection belongs in `shared/skills/manifests/roles/*.yaml` and `profiles/team-nexus.profiles.yaml`.
- Profile-local runtime skills under `runtime/hermes/profiles/<profile>/skills/` are allowed for local extensions, but they are not canonical and should not be the only copy of a team-required dispatcher skill.

After repairing shared skills, re-render and validate:

```bash
make profile-render
make validate
make doctor-all
```

## `Permission denied: '/opt/data/profiles/<profile>/auth.lock'`

What it means:

A profile runtime file or directory is not writable by the Hermes runtime user. The most common root cause is running profile commands as root inside Docker, which creates root-owned files under the mounted profile home.

Common bad pattern:

```bash
docker exec team-nexus-atlas-gateway hermes -p forge doctor
```

That command runs as root unless `docker exec -u` is specified. Prefer Makefile targets instead.

Safe patterns:

```bash
make hermes PROFILE=forge ARGS='doctor'
make doctor PROFILE=forge
make shell PROFILE=forge
```

If you must use `docker exec`, include the runtime UID/GID:

```bash
docker exec -u 1000:1000 team-nexus-atlas-gateway hermes -p forge doctor
```

Detect permission drift across active profiles:

```bash
make profile-permissions-check
```

Repair active profile runtime ownership/modes:

```bash
make profile-permissions-repair
make profile-permissions-check
```

The repair target runs inside the container and applies the configured host UID/GID from:

```text
TEAM_NEXUS_UID ?= $(id -u)
TEAM_NEXUS_GID ?= $(id -g)
```

Expected successful output:

```text
profile permissions OK: atlas, forge, sentinel, scribe, curator
```

## Runtime permission policy

Profile runtime homes live under:

```text
runtime/hermes/profiles/<profile>/
```

Inside the container they are mounted under:

```text
/opt/data/profiles/<profile>/
```

These profile runtime paths must be writable by the Hermes runtime user:

```text
.local/
cron/
hooks/
logs/
memories/
plans/
sessions/
skills/
skins/
workspace/
home/
```

These profile mounts are intentionally read-only and are ignored by the permission check:

```text
plugins/
dashboard-themes/
```

Sensitive runtime file modes:

```text
auth.json -> 0600
.env      -> 0600
auth.lock -> 0644
```

`profile-permissions.py` recursively checks nested runtime files and directories, does not follow symlinks during repair, and rejects auth/lock symlinks.

## Admin shells and root shells

Use this for normal operator inspection:

```bash
make shell PROFILE=forge
```

It opens a profile-scoped non-root shell with:

```text
HERMES_HOME=/opt/data/profiles/forge
```

Use this only for deliberate ownership repair or container administration:

```bash
make root-shell PROFILE=forge
```

After any root shell session, run:

```bash
make profile-permissions-check
```

If it fails, run:

```bash
make profile-permissions-repair
make profile-permissions-check
```

## Preflight catches profile permission drift

`make preflight` runs the normal validation/render path and then checks active profile runtime permissions:

```bash
make preflight
```

Equivalent relevant subcommands:

```bash
make validate
make profile-render-dry-run
make profile-render-docker-dry-run
make compose-config
make profile-render
make profile-permissions-check
```

Run preflight before starting or dispatching after profile/runtime changes.

## Do not commit runtime state or secrets

Never commit:

```text
runtime/
.env
runtime/hermes/profiles/*/auth.json
runtime/hermes/profiles/*/.env
runtime/hermes/profiles/*/sessions/
runtime/hermes/profiles/*/memories/
runtime/hermes/kanban/
```

Commit durable fixes instead:

- docs and ADRs for rationale,
- profile specs and `AGENTS.md` sources for active behavior,
- shared skills for reusable team procedures,
- Makefile/scripts/tests for repeatable operations.

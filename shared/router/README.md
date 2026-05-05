# Team Nexus Message Router

A lightweight stdlib-only message router for Team Nexus agent handoffs.

## Commands

```sh
python3 scripts/team-message-router.py init
python3 scripts/team-message-router.py send --from atlas --to forge --summary 'Build X' --goal 'Implement X' --deliverable 'Patch and tests'
python3 scripts/team-message-router.py list
python3 scripts/team-message-router.py inspect <message-id>
python3 scripts/team-message-router.py dispatch-pending --max 1 --dry-run
```

The default SQLite database is `shared/router/messages.db`. Dispatch writes JSON handoff artifacts to `shared/project/artifacts/router/` and, unless `--dry-run` is used, creates Kanban tasks through Docker Compose.

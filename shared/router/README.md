# Team Nexus Message Router

A lightweight stdlib-only message router for Team Nexus agent handoffs.

The router is the coordination/audit ledger. Kanban remains the execution ledger. Multi-agent fanout should start in the router so Atlas can cite conversation IDs, message IDs, and Kanban task IDs instead of making unverifiable claims that specialists were contacted.

## Commands

```sh
python3 scripts/team-message-router.py init
python3 scripts/team-message-router.py send --from atlas --to forge --summary 'Build X' --goal 'Implement X' --deliverable 'Patch and tests'
python3 scripts/team-message-router.py list
python3 scripts/team-message-router.py inspect <message-id>
python3 scripts/team-message-router.py dispatch-pending --max 1 --dry-run
python3 scripts/team-message-router.py sync-completions
python3 scripts/team-message-router.py conversation <conversation-id>
python3 scripts/team-message-router.py supervise --once --max 5 --create-report-tasks
```

The default SQLite database is `shared/router/messages.db`. Dispatch writes JSON handoff artifacts to `shared/project/artifacts/router/` and, unless `--dry-run` is used, creates Kanban tasks through Docker Compose.

## Supervisor

The supervisor command performs one or more passes of:

1. Dispatch pending router messages into Kanban tasks.
2. Sync terminal Kanban outcomes back into router message/conversation state.
3. Optionally create exactly one Atlas synthesis task for each terminal conversation.

Use Make targets for operations:

```sh
make router-supervisor-once MAX_MESSAGES=5 CREATE_REPORT_TASKS=1
ROUTER_SUPERVISOR_CREATE_REPORT_TASKS=1 make router-supervisor-daemon
make router-supervisor-logs
```

If Atlas synthesis tasks should be executed automatically by the Compose-aware Kanban dispatcher, also set `KANBAN_DISPATCH_INCLUDE_ATLAS=1` when starting the dispatcher.

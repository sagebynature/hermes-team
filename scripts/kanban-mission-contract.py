#!/usr/bin/env python3
"""Enforce the Team Nexus Kanban mission payload contract.

The mission notifier is deterministic only when every task can be associated
with a conversation/mission. This script installs SQLite triggers that reject
new or updated tasks missing the mission marker consumed by
scripts/kanban-mission-notifier.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KANBAN_HOME = Path(os.environ.get("HERMES_KANBAN_HOME", REPO_ROOT / "runtime" / "hermes" / "kanban"))
KANBAN_DB = DEFAULT_KANBAN_HOME / "kanban.db"

INSERT_TRIGGER = "enforce_team_nexus_mission_task_insert"
UPDATE_TRIGGER = "enforce_team_nexus_mission_task_update"

CONTRACT_ERROR = (
    "Team Nexus Kanban task rejected: every task must include a mission marker. "
    "Use a title containing [mission:<conversation_id>] and a body containing "
    "conversation_id: <conversation_id>."
)

MISSION_CONDITION = """
    coalesce(NEW.title, '') LIKE '%[mission:%]%'
    OR coalesce(NEW.body, '') LIKE '%conversation_id:%'
    OR coalesce(NEW.body, '') LIKE '%conversation_id=%'
    OR coalesce(NEW.idempotency_key, '') LIKE 'mission:%'
"""

SAMPLE_PAYLOAD = """[mission:mission_readiness_20260506] Readiness Check: Vega

conversation_id: mission_readiness_20260506
# Optional for Discord thread/forum-post routing when conversation_id is not the thread ID:
discord_thread_id: 1501451632569880636
reply_mode: atlas_internal
reply_expected: false
from: atlas
to: vega
assignee: vega
objective: Perform a one-paragraph readiness check for Sage.
constraints:
- Keep the response concise.
- Do not invent completed work or hidden context.
expected_output: >
  One paragraph covering responsibilities, one risk being watched, and one way
  Vega can help Sage this week.
artifact_path: /shared/project/artifacts/missions/mission_readiness_20260506/vega.md
reply_to: atlas
ttl: 1
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enforce/audit Team Nexus Kanban mission payloads")
    parser.add_argument("--db", default=str(KANBAN_DB), help="Path to shared kanban.db")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("install", help="Install SQLite triggers that reject non-mission tasks")
    sub.add_parser("uninstall", help="Remove mission contract enforcement triggers")
    sub.add_parser("check", help="Report existing tasks that do not satisfy the mission contract")
    sub.add_parser("sample-payload", help="Print a valid deterministic Kanban task payload")
    return parser.parse_args()


def connect(db: str | Path) -> sqlite3.Connection:
    path = Path(db)
    if not path.exists():
        raise SystemExit(f"missing Kanban DB: {path}; run `make kanban-init` first")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def install_triggers(conn: sqlite3.Connection) -> None:
    conn.executescript(
        f"""
        CREATE TRIGGER IF NOT EXISTS {INSERT_TRIGGER}
        BEFORE INSERT ON tasks
        WHEN NOT ({MISSION_CONDITION})
        BEGIN
            SELECT RAISE(ABORT, '{CONTRACT_ERROR}');
        END;

        CREATE TRIGGER IF NOT EXISTS {UPDATE_TRIGGER}
        BEFORE UPDATE OF title, body, idempotency_key ON tasks
        WHEN NOT ({MISSION_CONDITION})
        BEGIN
            SELECT RAISE(ABORT, '{CONTRACT_ERROR}');
        END;
        """
    )
    conn.commit()


def uninstall_triggers(conn: sqlite3.Connection) -> None:
    conn.executescript(
        f"""
        DROP TRIGGER IF EXISTS {INSERT_TRIGGER};
        DROP TRIGGER IF EXISTS {UPDATE_TRIGGER};
        """
    )
    conn.commit()


def non_compliant_tasks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, title, assignee, status, created_by, idempotency_key
          FROM tasks
         WHERE NOT (
            coalesce(title, '') LIKE '%[mission:%]%'
            OR coalesce(body, '') LIKE '%conversation_id:%'
            OR coalesce(body, '') LIKE '%conversation_id=%'
            OR coalesce(idempotency_key, '') LIKE 'mission:%'
         )
         ORDER BY created_at, id
        """
    ).fetchall()


def print_rows(rows: Iterable[sqlite3.Row]) -> None:
    for row in rows:
        print(
            json.dumps(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "assignee": row["assignee"],
                    "status": row["status"],
                    "created_by": row["created_by"],
                    "idempotency_key": row["idempotency_key"],
                },
                sort_keys=True,
            )
        )


def main() -> int:
    args = parse_args()
    if args.command == "sample-payload":
        print(SAMPLE_PAYLOAD.rstrip())
        return 0

    with connect(args.db) as conn:
        if args.command == "install":
            install_triggers(conn)
            print(f"installed mission contract triggers: {INSERT_TRIGGER}, {UPDATE_TRIGGER}")
            return 0
        if args.command == "uninstall":
            uninstall_triggers(conn)
            print(f"removed mission contract triggers: {INSERT_TRIGGER}, {UPDATE_TRIGGER}")
            return 0
        if args.command == "check":
            rows = non_compliant_tasks(conn)
            if not rows:
                print("all existing Kanban tasks satisfy the Team Nexus mission contract")
                return 0
            print(f"non-compliant existing Kanban tasks: {len(rows)}", file=sys.stderr)
            print_rows(rows)
            return 1

    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

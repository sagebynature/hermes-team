"""Regression tests for operator-facing Makefile contracts."""
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = REPO_ROOT / "Makefile"
COMPOSE_FILE = REPO_ROOT / "docker-compose.profiles.yml"
ATLAS_AGENTS = REPO_ROOT / "profiles" / "atlas" / "AGENTS.md"


class MakefileContractTests(unittest.TestCase):
    def test_kanban_create_exposes_workspace_selection(self):
        makefile = MAKEFILE.read_text()

        self.assertIn("WORKSPACE ?= scratch", makefile)
        self.assertIn("--workspace \"$(WORKSPACE)\"", makefile)
        self.assertIn("WORKSPACE=dir:/workspace", makefile)

    def test_mission_contract_and_notifier_use_profile_runtime_db(self):
        makefile = MAKEFILE.read_text()

        self.assertIn("KANBAN_DB ?= runtime/hermes/kanban/kanban.db", makefile)
        self.assertIn("kanban-init: profile-runtime-stage workspace-init", makefile)
        self.assertIn("kanban-mission-contract.py --db \"$(KANBAN_DB)\" install", makefile)
        self.assertIn("kanban-mission-notifier.py --db \"$(KANBAN_DB)\" --deliver", makefile)

    def test_compose_starts_mission_notifier_sidecar_by_default(self):
        compose = COMPOSE_FILE.read_text()

        self.assertIn("mission-notifier:", compose)
        self.assertNotIn("profiles: [\"notifier\"]", compose)
        self.assertIn("/workspace/scripts/kanban-mission-notifier.py", compose)
        self.assertIn("--db /opt/data/kanban/kanban.db", compose)
        self.assertIn("--deliver", compose)

    def test_atlas_profile_requires_mission_scoped_discord_tasks(self):
        agents = ATLAS_AGENTS.read_text()

        self.assertIn("title includes `[mission:<conversation_id>]`", agents)
        self.assertIn("body includes `conversation_id: <conversation_id>`", agents)
        self.assertIn("discord_thread_id: <thread-id>", agents)
        self.assertIn("reply_mode: direct_discord", agents)
        self.assertIn("kanban_complete(result=...)", agents)


if __name__ == "__main__":
    unittest.main()

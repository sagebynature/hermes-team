from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate-profile-spec.py"


def load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_profile_spec", VALIDATOR_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ProfileSpecValidatorTests(unittest.TestCase):
    def test_manifest_entries_must_resolve_to_shared_skill_dirs(self):
        validator = load_validator_module()
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "bad.yaml"
            manifest.write_text(
                "version: 0.1.0\n"
                "status: draft\n"
                "purpose: negative test\n"
                "skills:\n"
                "  - does-not-exist\n"
            )

            with self.assertRaisesRegex(validator.ValidationError, "missing shared skill"):
                validator.validate_manifest_file(manifest, "test.manifest")

    def test_current_planned_inactive_profiles_match_adr_0014(self):
        validator = load_validator_module()
        data = validator.load_yaml(REPO_ROOT / "profiles" / "team-nexus.profiles.yaml")
        planned = {
            profile["display_name"]
            for profile in data["profiles"].values()
            if profile.get("status") == "planned_inactive"
        }

        self.assertEqual(planned, {"Scout", "Ops", "Relay/Echo"})

    def test_gitignore_no_longer_contains_legacy_agents_runtime_policy(self):
        gitignore = (REPO_ROOT / ".gitignore").read_text()

        self.assertNotIn("agents/*/home", gitignore)
        self.assertNotIn("agents/*/workspace", gitignore)

    def test_atlas_has_messaging_toolset_for_direct_discord_synthesis(self):
        validator = load_validator_module()
        config = validator.load_yaml(REPO_ROOT / "profiles" / "atlas" / "config.yaml")

        self.assertIn("messaging", config["toolsets"])

    def test_atlas_direct_discord_policy_requires_verified_send_message_tool(self):
        agents = (REPO_ROOT / "profiles" / "atlas" / "AGENTS.md").read_text()

        self.assertIn("Do not use terminal or Hermes CLI commands as a substitute for the `send_message` tool", agents)
        self.assertIn("block the synthesis task instead of completing it", agents)


if __name__ == "__main__":
    unittest.main()

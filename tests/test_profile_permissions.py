from __future__ import annotations

import importlib.util
import os
import stat
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "profile-permissions.py"


def load_module():
    spec = importlib.util.spec_from_file_location("profile_permissions", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ProfilePermissionsTests(unittest.TestCase):
    def test_check_reports_unwritable_runtime_directory(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "profiles"
            profile = root / "forge"
            logs = profile / "logs"
            logs.mkdir(parents=True)
            logs.chmod(0o500)
            try:
                problems = mod.check_profiles(root, profiles=["forge"])
            finally:
                logs.chmod(0o700)

        self.assertTrue(any("logs" in problem.path for problem in problems), problems)
        self.assertTrue(any("not writable" in problem.message for problem in problems), problems)

    def test_check_reports_nested_unwritable_runtime_path(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "profiles"
            nested = root / "forge" / "skills" / ".hub"
            nested.mkdir(parents=True)
            nested.chmod(0o500)
            try:
                problems = mod.check_profiles(root, profiles=["forge"])
            finally:
                nested.chmod(0o700)

        self.assertTrue(any("skills/.hub" in problem.path for problem in problems), problems)

    def test_check_reports_untraversable_nested_runtime_directory(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "profiles"
            nested = root / "forge" / "logs" / "bad"
            nested.mkdir(parents=True)
            nested.chmod(0o000)
            try:
                problems = mod.check_profiles(root, profiles=["forge"])
            finally:
                nested.chmod(0o700)

        self.assertTrue(any("logs/bad" in problem.path for problem in problems), problems)

    def test_check_reports_symlinks_without_following_them(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "profiles"
            profile = root / "forge"
            profile.mkdir(parents=True)
            outside = Path(td) / "outside.txt"
            outside.write_text("do not touch")
            (profile / "auth.json").symlink_to(outside)

            problems = mod.check_profiles(root, profiles=["forge"])

        self.assertTrue(any("symlink" in problem.message for problem in problems), problems)

    def test_repair_restores_runtime_directory_writability_and_secret_modes(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "profiles"
            profile = root / "forge"
            logs = profile / "logs"
            skills = profile / "skills"
            logs.mkdir(parents=True)
            skills.mkdir()
            runtime_file = logs / "agent.log"
            auth_json = profile / "auth.json"
            env_file = profile / ".env"
            auth_lock = profile / "auth.lock"
            runtime_file.write_text("log")
            auth_json.write_text("{}")
            env_file.write_text("OPENROUTER_API_KEY=example")
            auth_lock.write_text("")
            logs.chmod(0o500)
            skills.chmod(0o555)
            runtime_file.chmod(0o400)
            auth_json.chmod(0o644)
            env_file.chmod(0o644)
            auth_lock.chmod(0o600)

            mod.repair_profiles(root, profiles=["forge"], uid=os.getuid(), gid=os.getgid())
            problems = mod.check_profiles(root, profiles=["forge"])

            self.assertEqual([], problems)
            self.assertTrue(os.access(runtime_file, os.W_OK))
            self.assertEqual(0o600, stat.S_IMODE(auth_json.stat().st_mode))
            self.assertEqual(0o600, stat.S_IMODE(env_file.stat().st_mode))
            self.assertEqual(0o644, stat.S_IMODE(auth_lock.stat().st_mode))

    def test_parse_profiles_accepts_makefile_space_separated_profile_list(self):
        mod = load_module()

        self.assertEqual(["atlas", "forge", "sentinel"], mod.parse_profiles("atlas forge,sentinel"))

    def test_repair_does_not_follow_symlink_targets(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "profiles"
            profile = root / "forge"
            profile.mkdir(parents=True)
            outside = Path(td) / "outside.txt"
            outside.write_text("do not chmod")
            outside.chmod(0o644)
            (profile / "auth.json").symlink_to(outside)

            mod.repair_profiles(root, profiles=["forge"], uid=os.getuid(), gid=os.getgid())

            self.assertEqual(0o644, stat.S_IMODE(outside.stat().st_mode))


if __name__ == "__main__":
    unittest.main()

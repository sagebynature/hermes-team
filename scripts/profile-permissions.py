#!/usr/bin/env python3
"""Check or repair writable Team Nexus Hermes profile runtime paths.

This script intentionally ignores read-only bind mounts under each profile home
(`plugins/` and `dashboard-themes/`). Everything else at the profile-runtime
layer must be writable by the Hermes runtime user, otherwise dispatcher-spawned
workers can crash on files like auth.lock, logs/, or skills/.hub.
"""
from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path
from typing import Iterable, NamedTuple

DEFAULT_PROFILES = ("atlas", "forge", "sentinel", "scribe", "curator")
DEFAULT_ROOT = Path("runtime/hermes/profiles")
READ_ONLY_TOP_LEVEL = {"plugins", "dashboard-themes"}
RUNTIME_DIRS = (
    "",
    ".local",
    "cron",
    "hooks",
    "logs",
    "memories",
    "plans",
    "sessions",
    "skills",
    "skins",
    "workspace",
    "home",
)
SECRET_FILES = {"auth.json", ".env"}
LOCK_FILES = {"auth.lock"}


class Problem(NamedTuple):
    profile: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.profile}: {self.path}: {self.message}"


def _profile_root(root: Path, profile: str) -> Path:
    return root / profile


def _is_ignored(path: Path, profile_root: Path) -> bool:
    try:
        rel = path.relative_to(profile_root)
    except ValueError:
        return False
    return bool(rel.parts) and rel.parts[0] in READ_ONLY_TOP_LEVEL


def _writable_probe(path: Path) -> bool:
    if path.is_dir():
        probe = path / ".team-nexus-write-test"
        try:
            probe.write_text("ok")
            probe.unlink()
            return True
        except OSError:
            return False
    return os.access(path, os.W_OK)


def iter_runtime_paths(root: Path, profile: str) -> Iterable[Path]:
    profile_root = _profile_root(root, profile)
    if not profile_root.exists():
        yield profile_root
        return

    yielded: set[Path] = set()
    for current, dirnames, filenames in os.walk(profile_root, topdown=True, followlinks=False):
        current_path = Path(current)
        if _is_ignored(current_path, profile_root):
            dirnames[:] = []
            continue
        if current_path not in yielded:
            yielded.add(current_path)
            yield current_path

        kept_dirnames: list[str] = []
        for dirname in dirnames:
            path = current_path / dirname
            if _is_ignored(path, profile_root):
                continue
            if path not in yielded:
                yielded.add(path)
                yield path
            if path.is_symlink():
                continue
            kept_dirnames.append(dirname)
        dirnames[:] = kept_dirnames

        for filename in filenames:
            path = current_path / filename
            if not _is_ignored(path, profile_root) and path not in yielded:
                yielded.add(path)
                yield path


def check_profiles(root: Path, profiles: Iterable[str] = DEFAULT_PROFILES) -> list[Problem]:
    root = Path(root)
    problems: list[Problem] = []
    for profile in profiles:
        profile_root = _profile_root(root, profile)
        for path in iter_runtime_paths(root, profile):
            display = str(path)
            if path.is_symlink():
                if path.name in SECRET_FILES or path.name in LOCK_FILES:
                    problems.append(Problem(profile, display, "symlink is not allowed for auth or lock files"))
                continue
            if not path.exists():
                problems.append(Problem(profile, display, "missing profile runtime path"))
                continue
            if _is_ignored(path, profile_root):
                continue
            if path.is_dir() and not _writable_probe(path):
                problems.append(Problem(profile, display, "directory is not writable by current user"))
            elif path.is_file() and not os.access(path, os.W_OK):
                problems.append(Problem(profile, display, "file is not writable by current user"))

            if path.is_file() and path.name in SECRET_FILES:
                mode = stat.S_IMODE(path.stat().st_mode)
                if mode != 0o600:
                    problems.append(Problem(profile, display, f"secret file mode is {mode:04o}, expected 0600"))
            if path.is_file() and path.name in LOCK_FILES:
                mode = stat.S_IMODE(path.stat().st_mode)
                if mode != 0o644:
                    problems.append(Problem(profile, display, f"lock file mode is {mode:04o}, expected 0644"))
    return problems


def _chown_if_requested(path: Path, uid: int | None, gid: int | None) -> None:
    if uid is None and gid is None:
        return
    os.chown(path, -1 if uid is None else uid, -1 if gid is None else gid)


def repair_profiles(
    root: Path,
    profiles: Iterable[str] = DEFAULT_PROFILES,
    *,
    uid: int | None = None,
    gid: int | None = None,
) -> None:
    root = Path(root)
    for profile in profiles:
        profile_root = _profile_root(root, profile)
        profile_root.mkdir(parents=True, exist_ok=True)
        for rel in RUNTIME_DIRS:
            path = profile_root / rel if rel else profile_root
            if rel:
                path.mkdir(parents=True, exist_ok=True)

        for current, dirnames, filenames in os.walk(profile_root, topdown=True, followlinks=False):
            current_path = Path(current)
            if _is_ignored(current_path, profile_root):
                dirnames[:] = []
                continue
            if current_path.is_symlink():
                dirnames[:] = []
                continue
            try:
                _chown_if_requested(current_path, uid, gid)
                current_path.chmod(0o700)
            except PermissionError:
                pass

            kept_dirnames: list[str] = []
            for dirname in dirnames:
                path = current_path / dirname
                if _is_ignored(path, profile_root):
                    continue
                if path.is_symlink():
                    continue
                kept_dirnames.append(dirname)
            dirnames[:] = kept_dirnames

            for filename in filenames:
                path = current_path / filename
                if _is_ignored(path, profile_root) or path.is_symlink():
                    continue
                try:
                    _chown_if_requested(path, uid, gid)
                    if path.name in SECRET_FILES:
                        path.chmod(0o600)
                    elif path.name in LOCK_FILES:
                        path.chmod(0o644)
                    else:
                        path.chmod(stat.S_IMODE(path.stat().st_mode) | stat.S_IRUSR | stat.S_IWUSR)
                except PermissionError:
                    pass


def parse_owner(value: str) -> tuple[int | None, int | None]:
    if not value:
        return None, None
    if ":" in value:
        uid_s, gid_s = value.split(":", 1)
    else:
        uid_s, gid_s = value, ""
    uid = int(uid_s) if uid_s else None
    gid = int(gid_s) if gid_s else None
    return uid, gid


def parse_profiles(value: str) -> list[str]:
    return [part for part in re.split(r"[\s,]+", value.strip()) if part]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "repair"))
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="profile runtime root")
    parser.add_argument("--profiles", default=",".join(DEFAULT_PROFILES), help="comma-separated profiles")
    parser.add_argument("--owner", default="", help="repair owner as uid:gid, e.g. 1000:1000")
    args = parser.parse_args(argv[1:])

    root = Path(args.root)
    profiles = parse_profiles(args.profiles)

    if args.action == "repair":
        uid, gid = parse_owner(args.owner)
        repair_profiles(root, profiles=profiles, uid=uid, gid=gid)

    problems = check_profiles(root, profiles=profiles)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print("profile permissions OK: " + ", ".join(profiles))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

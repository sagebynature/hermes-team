#!/usr/bin/env python3
"""Render Team Nexus Hermes profile files from repo-visible specs.

Default mode is dry-run: report what would be rendered without touching any
profile home. Use --write with --output-dir to materialize rendered files into a
staging directory. This early renderer intentionally refuses to write directly
into runtime-owned Hermes homes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
from pathlib import Path
from string import Template
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "profiles" / "team-nexus.profiles.yaml"
TEMPLATE_DIR = ROOT / "profiles" / "templates"
MANAGED_FILES = ("SOUL.md", "AGENTS.md", "config.yaml")


def load_validator_module():
    path = ROOT / "scripts" / "validate-profile-spec.py"
    spec = importlib.util.spec_from_file_location("team_nexus_profile_validator", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load validator module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_template(template_text: str, context: dict[str, Any]) -> str:
    # Convert the repo's {{ name }} placeholder style to string.Template.
    text = template_text
    for key in context:
        text = text.replace("{{ " + key + " }}", "${" + key + "}")
    return Template(text).safe_substitute({k: str(v) for k, v in context.items()})


def profile_context(name: str, profile: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    gateway = profile.get("gateway", {})
    checkpoints = profile.get("checkpoints", {})
    if args.mode == "docker":
        workspace_cwd = "/workspace"
        repo_root = "/workspace/team-nexus"
    else:
        workspace_cwd = str(ROOT)
        repo_root = str(ROOT)
    return {
        "profile": name,
        "display_name": profile.get("display_name", name.title()),
        "one_job": profile.get("one_job", "Team Nexus profile"),
        "summary": profile.get("summary", profile.get("one_job", "Team Nexus profile")),
        "gateway_enabled": str(bool(gateway.get("enabled"))).lower(),
        "checkpoints_enabled": str(bool(checkpoints.get("enabled"))).lower(),
        "workspace_cwd": workspace_cwd,
        "repo_root": repo_root,
    }


def rendered_files(data: dict[str, Any], args: argparse.Namespace) -> dict[Path, str]:
    profiles = data["profiles"]
    rendered: dict[Path, str] = {}
    for name, profile in profiles.items():
        if args.active_only and profile.get("status") != "active_v1":
            continue
        context = profile_context(name, profile, args)
        profile_root = Path(name)
        for filename in MANAGED_FILES:
            template_path = TEMPLATE_DIR / f"{filename}.tmpl"
            content = render_template(template_path.read_text(), context)
            rendered[profile_root / filename] = content
    return rendered


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", default=str(DEFAULT_SPEC), help="profile spec path")
    parser.add_argument("--mode", choices=("host", "docker"), default="host", help="render target mode")
    parser.add_argument("--active-only", action="store_true", default=True, help="render only active_v1 profiles")
    parser.add_argument("--include-planned", action="store_false", dest="active_only", help="also render planned inactive profiles")
    parser.add_argument("--write", action="store_true", help="write rendered files to --output-dir")
    parser.add_argument("--output-dir", default="", help="staging directory for --write")
    args = parser.parse_args(argv[1:])

    validator = load_validator_module()
    spec_path = Path(args.spec)
    if not spec_path.is_absolute():
        spec_path = Path.cwd() / spec_path
    validator.validate_spec(spec_path)
    data = validator.load_yaml(spec_path)

    files = rendered_files(data, args)
    if args.write:
        if not args.output_dir:
            print("--write requires --output-dir", file=sys.stderr)
            return 2
        output_dir = Path(args.output_dir)
        if not output_dir.is_absolute():
            output_dir = Path.cwd() / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        for rel, content in files.items():
            target = output_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        print(f"rendered {len(files)} files to {output_dir}")
    else:
        print(f"dry-run: would render {len(files)} files for mode={args.mode}")
        for rel, content in sorted(files.items()):
            print(f"{rel} sha256:{digest(content)} bytes:{len(content.encode())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

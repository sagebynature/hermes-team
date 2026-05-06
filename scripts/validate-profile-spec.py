#!/usr/bin/env python3
"""Validate the Team Nexus profile-driven runtime spec and profile sources.

The spec is intentionally lightweight: it owns the Team Nexus roster and
invariants. Native Hermes config.yaml files remain hand-maintained under
profiles/<profile>/config.yaml so this repo does not mirror Hermes' full config
schema.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "profiles" / "team-nexus.profiles.yaml"
ACTIVE_V1 = {"atlas", "forge", "sentinel", "scribe", "curator"}
TOP_LEVEL_REQUIRED = {
    "version",
    "status",
    "runtime",
    "interfaces",
    "kanban",
    "workspace",
    "knowledge",
    "profiles",
    "secrets",
    "verification_required_before_done",
}
PROFILE_REQUIRED = {"status", "display_name", "one_job", "gateway"}
ACTIVE_PROFILE_REQUIRED = {"summary", "skills", "owns", "checkpoints", "source_dir"}
NATIVE_STATUSES = {"triage", "todo", "ready", "running", "blocked", "done", "archived"}
PROFILE_SOURCE_FILES = ("SOUL.md", "AGENTS.md", "config.yaml")


class ValidationError(Exception):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    """Load YAML without requiring PyYAML.

    Prefer PyYAML when present. Fall back to Ruby's standard Psych YAML parser,
    which is available on macOS developer machines and avoids adding a Python
    dependency for this bootstrap validator.
    """
    try:
        import yaml  # type: ignore
    except ImportError:
        ruby = (
            "require 'yaml'; require 'json'; "
            "puts JSON.generate(YAML.load_file(ARGV.fetch(0)))"
        )
        try:
            proc = subprocess.run(
                ["ruby", "-e", ruby, str(path)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            detail = getattr(exc, "stderr", "") or str(exc)
            raise ValidationError(
                "cannot load YAML: install PyYAML or ensure Ruby is available; " + detail.strip()
            ) from exc
        return require_mapping(json.loads(proc.stdout), "spec")
    return require_mapping(yaml.safe_load(path.read_text()), "spec")


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{path} must be a mapping")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValidationError(f"{path} must be a list")
    return value


def validate_required_keys(mapping: dict[str, Any], required: set[str], path: str) -> None:
    missing = sorted(required - set(mapping))
    if missing:
        raise ValidationError(f"{path} missing required keys: {', '.join(missing)}")


def validate_repo_path(path_value: str, path_name: str) -> Path:
    path = ROOT / path_value
    if not path.exists():
        raise ValidationError(f"{path_name} does not exist: {path_value}")
    return path


def validate_manifest_path(path_value: str, profile: str) -> None:
    if not path_value:
        return
    validate_repo_path(path_value, f"profiles.{profile}.skills.role_manifest")


def validate_profile_source(profile_name: str, profile: dict[str, Any]) -> None:
    source_dir_value = profile.get("source_dir")
    if not isinstance(source_dir_value, str) or not source_dir_value:
        raise ValidationError(f"profiles.{profile_name}.source_dir must be a path string")
    source_dir = validate_repo_path(source_dir_value, f"profiles.{profile_name}.source_dir")
    if not source_dir.is_dir():
        raise ValidationError(f"profiles.{profile_name}.source_dir must be a directory: {source_dir_value}")
    for filename in PROFILE_SOURCE_FILES:
        path = source_dir / filename
        if not path.exists():
            raise ValidationError(f"profiles.{profile_name}.source_dir missing {filename}: {source_dir_value}")
        if not path.read_text().strip():
            raise ValidationError(f"profiles.{profile_name}.{filename} must not be empty")

    config = load_yaml(source_dir / "config.yaml")
    model = require_mapping(config.get("model"), f"profiles.{profile_name}.config.model")
    for key in ["provider", "default"]:
        if not isinstance(model.get(key), str) or not model.get(key):
            raise ValidationError(f"profiles.{profile_name}.config.model.{key} must be a non-empty string")
    dashboard = config.get("dashboard")
    if dashboard is not None:
        dashboard = require_mapping(dashboard, f"profiles.{profile_name}.config.dashboard")
        if dashboard.get("theme") != "team-nexus":
            raise ValidationError(f"profiles.{profile_name}.config.dashboard.theme must be team-nexus")


def validate_spec(spec_path: Path) -> list[str]:
    data = load_yaml(spec_path)
    validate_required_keys(data, TOP_LEVEL_REQUIRED, "spec")

    profiles = require_mapping(data["profiles"], "profiles")
    missing_active = sorted(ACTIVE_V1 - set(profiles))
    if missing_active:
        raise ValidationError(f"profiles missing active v1 profiles: {', '.join(missing_active)}")

    kanban = require_mapping(data["kanban"], "kanban")
    statuses = set(require_list(kanban.get("statuses_authoritative"), "kanban.statuses_authoritative"))
    if statuses != NATIVE_STATUSES:
        raise ValidationError(
            "kanban.statuses_authoritative must exactly match native Hermes statuses: "
            + ", ".join(sorted(NATIVE_STATUSES))
        )

    interfaces = require_mapping(data["interfaces"], "interfaces")
    discord = require_mapping(interfaces.get("discord"), "interfaces.discord")
    if discord.get("v1_gateway_profile") != "atlas":
        raise ValidationError("interfaces.discord.v1_gateway_profile must be atlas for v1")
    if discord.get("worker_gateways_default_enabled") is not False:
        raise ValidationError("worker gateways must be disabled by default in v1")

    atlas_gateway_enabled = False
    worker_gateway_violations: list[str] = []
    checkpoint_expected = {"forge", "sentinel", "scribe", "curator"}
    checkpoint_missing: list[str] = []

    for profile_name, profile_data in profiles.items():
        profile = require_mapping(profile_data, f"profiles.{profile_name}")
        validate_required_keys(profile, PROFILE_REQUIRED, f"profiles.{profile_name}")
        gateway = require_mapping(profile["gateway"], f"profiles.{profile_name}.gateway")
        checkpoints = require_mapping(profile.get("checkpoints", {}), f"profiles.{profile_name}.checkpoints")

        if profile_name == "atlas":
            atlas_gateway_enabled = gateway.get("enabled") is True
        elif gateway.get("enabled") is True:
            worker_gateway_violations.append(profile_name)

        if profile_name in checkpoint_expected and checkpoints.get("enabled") is not True:
            checkpoint_missing.append(profile_name)

        if profile.get("status") == "active_v1":
            validate_required_keys(profile, ACTIVE_PROFILE_REQUIRED, f"profiles.{profile_name}")
            validate_profile_source(profile_name, profile)
            skills = require_mapping(profile["skills"], f"profiles.{profile_name}.skills")
            base_manifest = skills.get("base_manifest")
            if not isinstance(base_manifest, str) or not base_manifest:
                raise ValidationError(f"profiles.{profile_name}.skills.base_manifest must be a path string")
            validate_repo_path(base_manifest, f"profiles.{profile_name}.skills.base_manifest")
            role_manifest = skills.get("role_manifest")
            if not isinstance(role_manifest, str) or not role_manifest:
                raise ValidationError(f"profiles.{profile_name}.skills.role_manifest must be a path string")
            validate_manifest_path(role_manifest, profile_name)
            owns = require_list(profile["owns"], f"profiles.{profile_name}.owns")
            if not owns:
                raise ValidationError(f"profiles.{profile_name}.owns must not be empty")

    if not atlas_gateway_enabled:
        raise ValidationError("Atlas gateway must be enabled in v1")
    if worker_gateway_violations:
        raise ValidationError("worker gateways must be disabled in v1: " + ", ".join(worker_gateway_violations))
    if checkpoint_missing:
        raise ValidationError("editing profiles must have checkpoints enabled: " + ", ".join(checkpoint_missing))

    secrets = require_mapping(data["secrets"], "secrets")
    if secrets.get("commit_real_secrets") is not False:
        raise ValidationError("secrets.commit_real_secrets must be false")
    if secrets.get("atlas_discord_token_required_v1") is not True:
        raise ValidationError("secrets.atlas_discord_token_required_v1 must be true")
    if secrets.get("worker_discord_tokens_optional_disabled_by_default") is not True:
        raise ValidationError("worker Discord tokens must be optional and disabled by default")

    required_checks = set(require_list(data["verification_required_before_done"], "verification_required_before_done"))
    for check in ["profile_spec_schema_validation", "docker_image_build", "first_vertical_slice", "no_committed_secrets"]:
        if check not in required_checks:
            raise ValidationError(f"verification_required_before_done missing {check}")

    if not (ROOT / "shared" / "dashboard-themes" / "team-nexus.yaml").is_file():
        raise ValidationError("shared/dashboard-themes/team-nexus.yaml is required for profile dashboards")

    return [
        f"profile spec OK: {spec_path}",
        "active profiles: " + ", ".join(sorted(ACTIVE_V1)),
        "profile sources: SOUL.md, AGENTS.md, config.yaml under profiles/<profile>/",
        "dashboard theme: team-nexus",
        "v1 gateway: atlas only",
        "editing checkpoints: forge, sentinel, scribe, curator",
    ]


def main(argv: list[str]) -> int:
    spec_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_SPEC
    if not spec_path.is_absolute():
        spec_path = Path.cwd() / spec_path
    try:
        for line in validate_spec(spec_path):
            print(line)
    except ValidationError as exc:
        print(f"profile spec invalid: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

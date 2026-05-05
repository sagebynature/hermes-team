#!/usr/bin/env python3
"""Registry-driven Team Nexus generation and validation.

Stdlib only. The YAML reader intentionally supports the simple Team Nexus files:
2-space-indented mappings, scalars, and block lists of scalars.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "shared" / "team-agents.yaml"
TEMPLATES_DIR = ROOT / "templates"
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]*$")
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class RegistryError(Exception):
    pass


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        return ""
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    if value in ("null", "None", "~"):
        return None
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(part.strip()) for part in inner.split(",")]
    return value


def read_simple_yaml(path: Path) -> Any:
    lines = path.read_text().splitlines()
    root: OrderedDict[str, Any] = OrderedDict()
    stack: list[tuple[int, Any]] = [(-1, root)]
    pending: tuple[int, OrderedDict[str, Any], str] | None = None

    for lineno, raw in enumerate(lines, 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith("\t"):
            raise RegistryError(f"{path}:{lineno}: tabs are not supported")
        indent = len(raw) - len(raw.lstrip(" "))
        if indent % 2:
            raise RegistryError(f"{path}:{lineno}: indentation must use multiples of two spaces")
        text = raw.strip()

        # Same-indentation list siblings belong to the current list; mapping
        # siblings at the same indentation close the previous container.
        while stack and indent <= stack[-1][0] and not (text.startswith("- ") and indent == stack[-1][0] and isinstance(stack[-1][1], list)):
            stack.pop()
        if not stack:
            raise RegistryError(f"{path}:{lineno}: invalid indentation")
        parent = stack[-1][1]

        if text.startswith("- "):
            item = parse_scalar(text[2:].strip())
            if not isinstance(parent, list):
                # Accept both canonical indented lists (key:\n  - item) and
                # common indentless block lists (key:\n- item), as emitted by
                # Hermes config.yaml today.
                if pending and indent in (pending[0], pending[0] - 2):
                    new_list: list[Any] = []
                    pending[1][pending[2]] = new_list
                    # Replace the placeholder mapping container, if it is still
                    # on the stack, with the actual list container.
                    while stack and stack[-1][0] >= indent:
                        stack.pop()
                    stack.append((indent, new_list))
                    parent = new_list
                    pending = None
                else:
                    raise RegistryError(f"{path}:{lineno}: list item without list parent")
            parent.append(item)
            continue

        if ":" not in text:
            # Minimal support for folded scalar continuation lines in existing
            # Hermes config.yaml files. Registry files should not rely on this.
            if indent > 0:
                continue
            raise RegistryError(f"{path}:{lineno}: expected key: value")
        if not isinstance(parent, dict):
            raise RegistryError(f"{path}:{lineno}: mapping entry under non-mapping")
        key, value = text.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise RegistryError(f"{path}:{lineno}: empty key")
        if value == "":
            child: OrderedDict[str, Any] = OrderedDict()
            parent[key] = child
            stack.append((indent, child))
            pending = (indent + 2, parent, key)
        else:
            parent[key] = parse_scalar(value)
            pending = None
    return root


def load_registry() -> OrderedDict[str, dict[str, Any]]:
    data = read_simple_yaml(REGISTRY_PATH)
    if not isinstance(data, dict) or "agents" not in data or not isinstance(data["agents"], dict):
        raise RegistryError("registry must contain top-level agents mapping")
    return data["agents"]


def as_bool(value: Any, field: str, slug: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    raise RegistryError(f"{slug}.{field} must be boolean")


def as_int(value: Any, field: str, slug: str) -> int:
    if isinstance(value, bool):
        raise RegistryError(f"{slug}.{field} must be integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise RegistryError(f"{slug}.{field} must be integer")


def validate_registry_data(agents: OrderedDict[str, dict[str, Any]]) -> None:
    errors: list[str] = []
    required = [
        "enabled", "service", "display_name", "role", "gateway_port", "dashboard_port",
        "dashboard_visible", "discord_visible", "dispatch_enabled",
    ]
    services: dict[str, str] = {}
    gateway_ports: dict[int, str] = {}
    dashboard_ports: dict[int, str] = {}
    default_routes: list[str] = []

    if "atlas" not in agents:
        errors.append("atlas must exist")
    for slug, info in agents.items():
        if not SLUG_RE.match(slug):
            errors.append(f"invalid slug: {slug}")
        if not isinstance(info, dict):
            errors.append(f"{slug}: registry entry must be a mapping")
            continue
        for field in required:
            if field not in info:
                errors.append(f"{slug}: missing {field}")
        try:
            enabled = as_bool(info.get("enabled"), "enabled", slug)
            dashboard_visible = as_bool(info.get("dashboard_visible"), "dashboard_visible", slug)
            as_bool(info.get("discord_visible"), "discord_visible", slug)
            as_bool(info.get("dispatch_enabled"), "dispatch_enabled", slug)
            if "default_route" in info and as_bool(info.get("default_route"), "default_route", slug) and enabled:
                default_routes.append(slug)
            service = str(info.get("service", ""))
            if not service:
                errors.append(f"{slug}: service is empty")
            elif service != slug:
                errors.append(f"{slug}: service must equal slug ({slug!r}); Compose service names and dispatcher routing use slug services")
            elif service in services:
                errors.append(f"duplicate service {service}: {services[service]} and {slug}")
            services[service] = slug
            gateway_port = as_int(info.get("gateway_port"), "gateway_port", slug)
            dashboard_port = as_int(info.get("dashboard_port"), "dashboard_port", slug)
            for field, port in (("gateway_port", gateway_port), ("dashboard_port", dashboard_port)):
                if port < 1 or port > 65535:
                    errors.append(f"{slug}: {field} must be between 1 and 65535; got {port}")
            for field in ("dashboard_primary_color", "dashboard_secondary_color"):
                if field in info and not HEX_COLOR_RE.fullmatch(str(info[field])):
                    errors.append(f"{slug}: {field} must be a 6-digit hex color like #50ff50")
            if enabled:
                if gateway_port in gateway_ports:
                    errors.append(f"duplicate gateway_port {gateway_port}: {gateway_ports[gateway_port]} and {slug}")
                gateway_ports[gateway_port] = slug
                if dashboard_visible:
                    if dashboard_port in dashboard_ports:
                        errors.append(f"duplicate dashboard_port {dashboard_port}: {dashboard_ports[dashboard_port]} and {slug}")
                    dashboard_ports[dashboard_port] = slug
        except RegistryError as exc:
            errors.append(str(exc))
    if "atlas" in agents:
        try:
            if not as_bool(agents["atlas"].get("enabled"), "enabled", "atlas"):
                errors.append("atlas must be enabled")
        except RegistryError as exc:
            errors.append(str(exc))
    if len(default_routes) != 1:
        errors.append(f"exactly one enabled agent must have default_route: true; found {default_routes or 'none'}")
    elif default_routes[0] != "atlas":
        errors.append("atlas must be the default_route agent for current generated nginx behavior")

    if errors:
        raise RegistryError("registry validation failed:\n" + "\n".join(f"- {e}" for e in errors))


def agents_all() -> OrderedDict[str, dict[str, Any]]:
    agents = load_registry()
    validate_registry_data(agents)
    return agents


def enabled_agents(agents: OrderedDict[str, dict[str, Any]]) -> OrderedDict[str, dict[str, Any]]:
    return OrderedDict((s, i) for s, i in agents.items() if as_bool(i["enabled"], "enabled", s))


def dashboard_agents(agents: OrderedDict[str, dict[str, Any]]) -> OrderedDict[str, dict[str, Any]]:
    return OrderedDict((s, i) for s, i in enabled_agents(agents).items() if as_bool(i["dashboard_visible"], "dashboard_visible", s))


def default_route_slug(agents: OrderedDict[str, dict[str, Any]]) -> str:
    for slug, info in enabled_agents(agents).items():
        if as_bool(info.get("default_route", False), "default_route", slug):
            return slug
    return "atlas"


def emit_make(agents: OrderedDict[str, dict[str, Any]]) -> str:
    enabled = " ".join(enabled_agents(agents).keys())
    dashboards = " ".join(dashboard_agents(agents).keys())
    return "\n".join([
        "# GENERATED FILE. DO NOT EDIT.",
        "# Source: shared/team-agents.yaml",
        "# Regenerate: make generate",
        f"TEAM_AGENTS := {enabled}",
        f"DASHBOARD_AGENTS := {dashboards}",
        "",
    ])


def compose_quote(value: Any) -> str:
    text = str(value)
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def agent_volumes(slug: str, comments: bool = False) -> list[str]:
    lines: list[str] = []
    if comments:
        lines.append("      # Hermes Docker docs use /opt/data for durable user data: config, auth state, sessions, skills, memories.")
    lines.append(f"      - ./agents/{slug}/home:/opt/data")
    if comments:
        lines.append("      # Agent-owned workspace. Configure terminal.cwd=/workspace in config.yaml.")
    lines.append(f"      - ./agents/{slug}/workspace:/workspace")
    if comments:
        lines.append("      # Shared project context is read-only, except the artifacts submount below is writable for handoffs.")
    lines += [
        "      - ./shared/project:/shared/project:ro",
        "      - ./shared/project/artifacts:/shared/project/artifacts:rw",
    ]
    if comments:
        lines.append("      # Shared writable Kanban board root (SQLite DB, workspaces, worker logs).")
    lines += [
        "      - ./shared/kanban:/shared/kanban:rw",
        "      - ./shared/router:/shared/router:rw",
        "      - ./shared/skills:/shared/skills:ro",
        "      - ./shared/mcp:/shared/mcp:ro",
    ]
    if comments:
        lines.append("      # Hermes only discovers user plugins under $HERMES_HOME/plugins.")
    lines += [
        "      - ./shared/plugins:/opt/data/plugins:ro",
        "      - ./shared/dashboard-themes:/opt/data/dashboard-themes:ro",
    ]
    return lines


def emit_agent_service(slug: str, info: dict[str, Any]) -> list[str]:
    lines = [
        f"  {slug}:",
    ]
    if slug == "atlas":
        lines += ["    build:", "      context: ./docker"]
    lines += [
        "    image: team-nexus-agent:latest",
        f"    container_name: hermes-{slug}",
        "    restart: unless-stopped",
        "    environment:",
        "      HERMES_HOME: /opt/data",
        "      HERMES_KANBAN_HOME: /shared/kanban",
        "      # Match the container runtime user to the host operator so bind-mounted",
        "      # agent homes stay browsable/editable after startup on Linux.",
        "      HERMES_UID: ${TEAM_NEXUS_UID:-10000}",
        "      HERMES_GID: ${TEAM_NEXUS_GID:-10000}",
        f"      AGENT_NAME: {compose_quote(info['display_name'])}",
        f"      AGENT_ROLE: {compose_quote(info['role'])}",
        "    env_file:",
        "      - ./.env",
        "    volumes:",
        *agent_volumes(slug, comments=True),
        "    ports:",
        f"      - \"127.0.0.1:{info['gateway_port']}:8642\"",
        "    command: [\"gateway\", \"run\"]",
        "",
    ]
    return lines


def emit_dashboard_service(slug: str, info: dict[str, Any]) -> list[str]:
    return [
        f"  {slug}-dashboard:",
        "    image: team-nexus-agent:latest",
        f"    container_name: hermes-{slug}-dashboard",
        "    restart: unless-stopped",
        "    profiles: [\"dashboard\"]",
        "    environment:",
        "      HERMES_HOME: /opt/data",
        "      HERMES_KANBAN_HOME: /shared/kanban",
        "      # Match the container runtime user to the host operator so bind-mounted",
        "      # agent homes stay browsable/editable after startup on Linux.",
        "      HERMES_UID: ${TEAM_NEXUS_UID:-10000}",
        "      HERMES_GID: ${TEAM_NEXUS_GID:-10000}",
        f"      AGENT_NAME: {compose_quote(info['display_name'])}",
        f"      AGENT_ROLE: {compose_quote(info['role'])}",
        "    env_file:",
        "      - ./.env",
        "    volumes:",
        *agent_volumes(slug),
        "    ports:",
        f"      - \"127.0.0.1:{info['dashboard_port']}:9119\"",
        "    command: [\"dashboard\", \"--host\", \"0.0.0.0\", \"--port\", \"9119\", \"--insecure\", \"--no-open\"]",
        "",
    ]


def emit_compose_agents(agents: OrderedDict[str, dict[str, Any]]) -> str:
    lines = [
        "# GENERATED FILE. DO NOT EDIT.",
        "# Source: shared/team-agents.yaml",
        "# Regenerate: make generate",
        "services:",
    ]
    for slug, info in enabled_agents(agents).items():
        lines += emit_agent_service(slug, info)
    if len(lines) == 4:
        lines.append("  {}"); lines.append("")
    return "\n".join(lines)


def emit_compose_dashboards(agents: OrderedDict[str, dict[str, Any]]) -> str:
    dashboards = dashboard_agents(agents)
    lines = [
        "# GENERATED FILE. DO NOT EDIT.",
        "# Source: shared/team-agents.yaml",
        "# Regenerate: make generate",
        "services:",
    ]
    for slug, info in dashboards.items():
        lines += emit_dashboard_service(slug, info)
    lines += [
        "  dashboard-nginx:",
        "    image: nginx:1.27-alpine",
        "    container_name: hermes-dashboard-nginx",
        "    restart: unless-stopped",
        "    profiles: [\"dashboard\"]",
    ]
    if dashboards:
        lines.append("    depends_on:")
        for slug in dashboards:
            lines.append(f"      - {slug}-dashboard")
    lines += [
        "    ports:",
        "      - \"127.0.0.1:${NGINX_PORT:-9130}:80\"",
        "    volumes:",
        "      - ./nginx/dashboards.conf:/etc/nginx/conf.d/default.conf:ro",
        "",
    ]
    return "\n".join(lines)


SUB_FILTER_PATHS = ["sessions", "analytics", "models", "logs", "cron", "skills", "plugins", "profiles", "config", "env", "docs", "chat", "kanban", "command-center", "team-router"]
PLUGIN_PREFIXES = ["command-center", "achievements", "kanban", "team-router", "example"]
DASHBOARD_SHORTCUT_PATHS = ["sessions", "kanban", "command-center", "team-router"]


def nginx_block(slug: str) -> str:
    lines = [
        f"  location = /{slug} {{",
        f"    return 302 /{slug}/sessions;",
        "  }",
        "",
        f"  location = /{slug}/ {{",
        f"    return 302 /{slug}/sessions;",
        "  }",
        "",
        f"  location /{slug}/ {{",
        f"    proxy_pass http://{slug}-dashboard:9119/;",
        "    proxy_http_version 1.1;",
        "    proxy_set_header Host $host;",
        "    proxy_set_header X-Real-IP $remote_addr;",
        "    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        "    proxy_set_header X-Forwarded-Proto $scheme;",
        f"    proxy_set_header X-Forwarded-Prefix /{slug};",
        "    proxy_set_header Upgrade $http_upgrade;",
        "    proxy_set_header Connection $connection_upgrade;",
        "    proxy_set_header Accept-Encoding \"\";",
        f"    proxy_redirect ~^(/.*)$ /{slug}$1;",
        "    sub_filter_once off;",
        "    sub_filter_types text/css application/javascript text/javascript application/json;",
        f"    sub_filter 'href=\"/' 'href=\"/{slug}/';",
        f"    sub_filter 'src=\"/' 'src=\"/{slug}/';",
        f"    sub_filter 'content=\"/' 'content=\"/{slug}/';",
        f"    sub_filter 'url(/' 'url(/{slug}/';",
        f"    sub_filter '\"/dashboard-plugins/' '\"/{slug}/dashboard-plugins/';",
        f"    sub_filter '`/dashboard-plugins/' '`/{slug}/dashboard-plugins/';",
        f"    sub_filter '\"/dashboard-themes/' '\"/{slug}/dashboard-themes/';",
        f"    sub_filter '`/dashboard-themes/' '`/{slug}/dashboard-themes/';",
        f"    sub_filter '\"/api/' '\"/{slug}/api/';",
        f"    sub_filter '`/api/' '`/{slug}/api/';",
        f"    sub_filter 'location.host+\"/api/' 'location.host+\"/{slug}/api/';",
    ]
    for path in SUB_FILTER_PATHS:
        lines.append(f"    sub_filter '\"/{path}\"' '\"/{slug}/{path}\"';")
        lines.append(f"    sub_filter '`/{path}`' '`/{slug}/{path}`';")
    for plugin in PLUGIN_PREFIXES:
        lines.append(f"    sub_filter '\"/plugins/{plugin}' '\"/{slug}/plugins/{plugin}';")
        lines.append(f"    sub_filter '`/plugins/{plugin}' '`/{slug}/plugins/{plugin}';")
    lines += ["  }"]
    return "\n".join(lines)


def nginx_shortcuts(default_slug: str) -> str:
    lines: list[str] = []
    for path in DASHBOARD_SHORTCUT_PATHS:
        lines += [
            f"  location = /{path} {{",
            f"    return 302 /{default_slug}/{path};",
            "  }",
            "",
            f"  location = /{path}/ {{",
            f"    return 302 /{default_slug}/{path};",
            "  }",
            "",
        ]
    return "\n".join(lines).rstrip()


def emit_nginx(agents: OrderedDict[str, dict[str, Any]]) -> str:
    default = default_route_slug(agents)
    shortcuts = nginx_shortcuts(default)
    locations = "\n\n".join(nginx_block(slug) for slug in dashboard_agents(agents))
    if locations:
        locations += "\n"
    return render_template("dashboards.conf.tmpl", {
        "default_route": default,
        "dashboard_shortcuts": shortcuts,
        "dashboard_locations": locations,
    })


def emit_roster(agents: OrderedDict[str, dict[str, Any]]) -> str:
    lines = [
        "# Generated Team Nexus roster",
        "",
        "This file is generated from `shared/team-agents.yaml`. Regenerate with `make generate`.",
        "",
        "Allowed Kanban assignees:",
        "",
    ]
    for slug, info in enabled_agents(agents).items():
        lines.append(f"- {slug}: {info['display_name']} — {info['role']}")
    lines.append("")
    return "\n".join(lines)


def print_list(slugs) -> None:
    print(" ".join(slugs))


def next_ports(agents) -> tuple[int, int]:
    used_gateways = {as_int(i["gateway_port"], "gateway_port", s) for s, i in agents.items() if "gateway_port" in i}
    used_dashboards = {as_int(i["dashboard_port"], "dashboard_port", s) for s, i in agents.items() if "dashboard_port" in i}
    gw = max(used_gateways or {8641}) + 1
    while gw in used_gateways:
        gw += 1
    dash = max(used_dashboards or {9118}) + 1
    while dash in used_dashboards:
        dash += 1
    return gw, dash


def cmd_next_ports(agents) -> None:
    gw, dash = next_ports(agents)
    print(f"gateway_port: {gw}")
    print(f"dashboard_port: {dash}")


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if value is None:
        return "null"
    text = str(value)
    if text == "" or text.strip() != text or any(ch in text for ch in [":", "#", "'", '"']):
        return "'" + text.replace("'", "''") + "'"
    return text


def write_registry(agents: OrderedDict[str, dict[str, Any]]) -> None:
    lines = ["agents:"]
    ordered_fields = [
        "enabled", "archived", "service", "display_name", "role", "gateway_port", "dashboard_port",
        "dashboard_visible", "discord_visible", "dispatch_enabled", "default_route",
    ]
    for slug, info in agents.items():
        lines.append(f"  {slug}:")
        for field in ordered_fields:
            if field in info:
                lines.append(f"    {field}: {yaml_scalar(info[field])}")
        for field, value in info.items():
            if field not in ordered_fields:
                lines.append(f"    {field}: {yaml_scalar(value)}")
    REGISTRY_PATH.write_text("\n".join(lines) + "\n")


def render_template(name: str, values: dict[str, Any]) -> str:
    path = TEMPLATES_DIR / name
    if not path.exists():
        raise RegistryError(f"missing template: templates/{name}")
    text = path.read_text()
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def create_agent_files(slug: str, info: dict[str, Any]) -> None:
    base = ROOT / "agents" / slug
    home = base / "home"
    workspace = base / "workspace"
    if base.exists():
        raise RegistryError(f"agents/{slug} already exists; refusing to overwrite")
    for path in [home, workspace / "inbox", workspace / "outbox", workspace / "artifacts", workspace / "notes"]:
        path.mkdir(parents=True, exist_ok=False)
    values = {
        "slug": slug,
        "name": info["display_name"],
        "role": info["role"],
        "gateway_port": info["gateway_port"],
        "dashboard_port": info["dashboard_port"],
        "dashboard_primary_color": info.get("dashboard_primary_color", "#50ff50"),
        "dashboard_secondary_color": info.get("dashboard_secondary_color", "#ff9830"),
    }
    (home / "config.yaml").write_text(render_template("agent-config.yaml.tmpl", values))
    (home / "SOUL.md").write_text(render_template("agent-SOUL.md.tmpl", values))
    (home / "AGENTS.md").write_text(render_template("agent-AGENTS.md.tmpl", values))
    (workspace / ".mise.toml").write_text("# Optional agent-local mise tools.\n# [tools]\n# node = \"lts\"\n")


def cmd_agent_add(args: argparse.Namespace, agents: OrderedDict[str, dict[str, Any]]) -> None:
    slug = args.slug
    if not SLUG_RE.match(slug):
        raise RegistryError(f"invalid slug {slug!r}; expected {SLUG_RE.pattern}")
    if slug in agents:
        raise RegistryError(f"registry already contains {slug}; refusing to overwrite")
    validate_registry_data(agents)
    gw, dash = next_ports(agents)
    if args.gateway_port is not None:
        gw = args.gateway_port
    if args.dashboard_port is not None:
        dash = args.dashboard_port
    existing_gw = {as_int(i["gateway_port"], "gateway_port", s) for s, i in agents.items() if "gateway_port" in i}
    existing_dash = {as_int(i["dashboard_port"], "dashboard_port", s) for s, i in agents.items() if "dashboard_port" in i}
    if gw in existing_gw:
        raise RegistryError(f"gateway_port {gw} is already in use")
    if dash in existing_dash:
        raise RegistryError(f"dashboard_port {dash} is already in use")
    info = OrderedDict([
        ("enabled", True),
        ("service", slug),
        ("display_name", args.name),
        ("role", args.role),
        ("gateway_port", gw),
        ("dashboard_port", dash),
        ("dashboard_visible", True),
        ("discord_visible", True),
        ("dispatch_enabled", True),
    ])
    agents[slug] = info
    validate_registry_data(agents)
    create_agent_files(slug, info)
    write_registry(agents)
    print(f"added agent {slug} ({args.name}) gateway_port={gw} dashboard_port={dash}")


def optional_env_int(name: str) -> int | None:
    value = os.environ.get(name, "")
    if value == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise RegistryError(f"{name} must be an integer") from exc


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        raise RegistryError(f"{name} environment variable is required")
    return value


def cmd_agent_add_env(agents: OrderedDict[str, dict[str, Any]]) -> None:
    args = argparse.Namespace(
        slug=required_env("SLUG"),
        name=required_env("NAME"),
        role=required_env("ROLE"),
        gateway_port=optional_env_int("GATEWAY_PORT"),
        dashboard_port=optional_env_int("DASHBOARD_PORT"),
    )
    cmd_agent_add(args, agents)


def cmd_agent_disable_env(agents: OrderedDict[str, dict[str, Any]]) -> None:
    cmd_agent_disable(argparse.Namespace(slug=required_env("SLUG")), agents)


def cmd_agent_archive_env(agents: OrderedDict[str, dict[str, Any]]) -> None:
    force = os.environ.get("FORCE", "") not in ("", "0", "false", "False", "no", "No")
    cmd_agent_archive(argparse.Namespace(slug=required_env("SLUG"), force=force), agents)


def quote_sqlite_identifier(identifier: str) -> str:
    if "\x00" in identifier:
        raise RegistryError("sqlite identifier contains NUL byte")
    return '"' + identifier.replace('"', '""') + '"'


def warn_open_kanban_tasks(slug: str) -> None:
    db = ROOT / "shared" / "kanban" / "kanban.db"
    if not db.exists():
        return
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        print(f"warning: cannot inspect kanban db read-only ({exc})", file=sys.stderr)
        return
    closed_statuses = {"done", "closed", "complete", "completed", "archived", "cancelled", "canceled"}
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        warnings: list[str] = []
        for table in tables:
            table_q = quote_sqlite_identifier(table)
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table_q})")]
            assignee_col = next((c for c in ("assignee", "assigned_to") if c in cols), None)
            if not assignee_col:
                continue
            status_col = next((c for c in ("status", "state", "column") if c in cols), None)
            id_col = next((c for c in ("id", "task_id") if c in cols), "rowid")
            title_col = next((c for c in ("title", "summary", "name") if c in cols), None)
            fields = [id_col, assignee_col]
            if status_col:
                fields.append(status_col)
            if title_col:
                fields.append(title_col)
            select_fields = ", ".join("rowid" if f == "rowid" else quote_sqlite_identifier(f) for f in fields)
            assignee_q = quote_sqlite_identifier(assignee_col)
            q = f"SELECT {select_fields} FROM {table_q} WHERE {assignee_q} = ?"
            for row in conn.execute(q, (slug,)):
                row_map = dict(zip(fields, row))
                status = str(row_map.get(status_col, "open") or "").lower() if status_col else "open"
                if status not in closed_statuses:
                    label = row_map.get(id_col)
                    title = row_map.get(title_col, "") if title_col else ""
                    warnings.append(f"{table} {label}: status={status or 'open'} {title}".strip())
        for warning in warnings:
            print(f"warning: open Kanban task assigned to disabled agent {slug}: {warning}", file=sys.stderr)
    finally:
        conn.close()


def cmd_agent_disable(args: argparse.Namespace, agents: OrderedDict[str, dict[str, Any]]) -> None:
    slug = args.slug
    if slug not in agents:
        raise RegistryError(f"unknown agent {slug}")
    if slug == "atlas":
        raise RegistryError("refusing to disable atlas; atlas must remain enabled")
    info = agents[slug]
    info["enabled"] = False
    info["dashboard_visible"] = False
    info["discord_visible"] = False
    info["dispatch_enabled"] = False
    write_registry(agents)
    warn_open_kanban_tasks(slug)
    print(f"disabled agent {slug}; files under agents/{slug} were preserved")
    print("run `make generate` to refresh generated runtime artifacts")


def cmd_agent_archive(args: argparse.Namespace, agents: OrderedDict[str, dict[str, Any]]) -> None:
    slug = args.slug
    if slug not in agents:
        raise RegistryError(f"unknown agent {slug}")
    if slug == "atlas":
        raise RegistryError("refusing to archive atlas")
    info = agents[slug]
    if as_bool(info.get("enabled", False), "enabled", slug) and not args.force:
        raise RegistryError(f"agent {slug} is still enabled; run agent-disable first or pass --force")
    src = ROOT / "agents" / slug
    archive_root = ROOT / "agents" / ".archived"
    if src.exists():
        archive_root.mkdir(parents=True, exist_ok=True)
        date = datetime.now().strftime("%Y%m%d")
        dest = archive_root / f"{slug}-{date}"
        suffix = 1
        while dest.exists():
            suffix += 1
            dest = archive_root / f"{slug}-{date}-{suffix}"
        shutil.move(str(src), str(dest))
        print(f"archived files: agents/{slug} -> {dest.relative_to(ROOT)}")
        print(f"warning: archived home may contain auth tokens or secrets; review {dest.relative_to(ROOT)} before sharing", file=sys.stderr)
    else:
        print(f"warning: agents/{slug} does not exist; marking registry entry archived only", file=sys.stderr)
    info["enabled"] = False
    info["dashboard_visible"] = False
    info["discord_visible"] = False
    info["dispatch_enabled"] = False
    info["archived"] = True
    write_registry(agents)
    print(f"marked agent {slug} archived in shared/team-agents.yaml")
    print("run `make generate` to refresh generated runtime artifacts")


def validate_filesystem(agents) -> None:
    errors: list[str] = []
    warnings: list[str] = []
    required = [
        "home/config.yaml", "home/SOUL.md", "home/AGENTS.md", "workspace", "workspace/inbox",
        "workspace/outbox", "workspace/artifacts", "workspace/notes",
    ]
    for slug in enabled_agents(agents):
        base = ROOT / "agents" / slug
        for rel in required:
            if not (base / rel).exists():
                errors.append(f"missing agents/{slug}/{rel}")
        if not (base / "workspace/.mise.toml").exists():
            warnings.append(f"optional missing agents/{slug}/workspace/.mise.toml")
    known = set(agents.keys())
    agents_dir = ROOT / "agents"
    for child in agents_dir.iterdir() if agents_dir.exists() else []:
        if child.name.startswith("."):
            continue
        if child.is_dir() and child.name not in known:
            errors.append(f"unknown agent directory agents/{child.name}")
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if errors:
        raise RegistryError("filesystem validation failed:\n" + "\n".join(f"- {e}" for e in errors))


def get_path(data: Any, dotted: str) -> Any:
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def validate_configs(agents) -> None:
    errors: list[str] = []
    for slug, info in enabled_agents(agents).items():
        path = ROOT / "agents" / slug / "home" / "config.yaml"
        try:
            cfg = read_simple_yaml(path)
        except Exception as exc:
            errors.append(f"{path.relative_to(ROOT)}: cannot parse: {exc}")
            continue
        expected = {
            "terminal.cwd": "/workspace",
            "kanban.dispatch_in_gateway": False,
            "security.redact_secrets": True,
            "startup_agent.slug": slug,
            "startup_agent.name": info["display_name"],
            "startup_agent.role": info["role"],
            "dashboard.agent_name": "${AGENT_NAME}",
            "dashboard.agent_role": "${AGENT_ROLE}",
        }
        for dotted, value in expected.items():
            got = get_path(cfg, dotted)
            if got != value:
                errors.append(f"{path.relative_to(ROOT)}: {dotted} expected {value!r}, got {got!r}")
        toolsets = cfg.get("toolsets") if isinstance(cfg, dict) else None
        if not isinstance(toolsets, list) or "hermes-cli" not in toolsets or "kanban" not in toolsets:
            errors.append(f"{path.relative_to(ROOT)}: toolsets must include hermes-cli and kanban")
    if errors:
        raise RegistryError("config validation failed:\n" + "\n".join(f"- {e}" for e in errors))


def run_compose_config() -> str | None:
    cmd = [
        "docker", "compose",
        "-f", "docker-compose.yml",
        "-f", "docker-compose.agents.generated.yml",
        "-f", "docker-compose.dashboards.generated.yml",
        "--profile", "dashboard", "--profile", "dispatcher", "config",
    ]
    try:
        proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    except FileNotFoundError:
        print("warning: docker not found; skipping compose config validation", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired as exc:
        raise RegistryError(f"docker compose config timed out: {exc}")
    if proc.returncode != 0:
        raise RegistryError("docker compose config failed:\n" + proc.stderr.strip())
    return proc.stdout


def validate_compose_port_bindings(rendered: str) -> list[str]:
    errors: list[str] = []
    lines = rendered.splitlines()
    in_ports = False
    current: dict[str, str] | None = None

    def finish(entry: dict[str, str] | None) -> None:
        if not entry:
            return
        target = entry.get("target", "").strip().strip('"')
        if target not in {"80", "8642", "9119"}:
            return
        if "published" not in entry:
            return
        host_ip = (entry.get("host_ip") or entry.get("host_ip_address") or "").strip().strip('"')
        if host_ip != "127.0.0.1":
            errors.append(f"published target {target} port must explicitly bind host_ip 127.0.0.1; found {host_ip or 'missing'}")

    for line in lines:
        if re.match(r"^    ports:\s*$", line):
            finish(current); current = None; in_ports = True; continue
        if in_ports and re.match(r"^    [A-Za-z0-9_.-]+:", line):
            finish(current); current = None; in_ports = False; continue
        if not in_ports:
            continue
        if re.match(r"^      - ", line):
            finish(current)
            current = {}
            text = line.split("-", 1)[1].strip().strip('"')
            inline = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", text)
            if inline:
                current[inline.group(1)] = inline.group(2).strip()
            # Short syntax should not normally appear after docker compose config,
            # but fail closed unless it explicitly starts with 127.0.0.1:.
            elif text and ":" in text:
                parts = text.split(":")
                if parts[0] != "127.0.0.1":
                    errors.append(f"published port short syntax must explicitly bind 127.0.0.1: {text}")
                if len(parts) >= 3:
                    current = {"host_ip": parts[0], "published": parts[1], "target": parts[2]}
            continue
        if current is not None:
            m = re.match(r"^        ([A-Za-z0-9_]+):\s*(.*)$", line)
            if m:
                current[m.group(1)] = m.group(2).strip()
    finish(current)
    return errors


def validate_compose(agents) -> None:
    rendered = run_compose_config()
    if rendered is None:
        return
    errors: list[str] = []
    # Text checks intentionally preserve current hand-authored Compose architecture.
    for slug in enabled_agents(agents):
        if not re.search(rf"(?m)^  {re.escape(slug)}:\n", rendered):
            errors.append(f"missing gateway service {slug}")
        port = agents[slug]["gateway_port"]
        if f"127.0.0.1:{port}:8642" not in rendered and f"published: \"{port}\"" not in rendered:
            errors.append(f"gateway {slug} missing localhost published port {port}")
    for slug in dashboard_agents(agents):
        if not re.search(rf"(?m)^  {re.escape(slug)}-dashboard:\n", rendered):
            errors.append(f"missing dashboard service {slug}-dashboard")
        port = agents[slug]["dashboard_port"]
        if f"127.0.0.1:{port}:9119" not in rendered and f"published: \"{port}\"" not in rendered:
            errors.append(f"dashboard {slug} missing localhost published port {port}")
    if not re.search(r"(?m)^  kanban-dispatcher:\n", rendered):
        errors.append("missing dispatcher service")
    disabled = [s for s, i in agents.items() if not as_bool(i["enabled"], "enabled", s)]
    for slug in disabled:
        if re.search(rf"(?m)^  {re.escape(slug)}:\n", rendered) or re.search(rf"(?m)^  {re.escape(slug)}-dashboard:\n", rendered):
            errors.append(f"disabled service appears in compose: {slug}")
    errors += validate_compose_port_bindings(rendered)
    if errors:
        raise RegistryError("compose validation failed:\n" + "\n".join(f"- {e}" for e in errors))


def validate_nginx(agents) -> None:
    path = ROOT / "nginx" / "dashboards.conf"
    if not path.exists():
        raise RegistryError("nginx/dashboards.conf is missing")
    text = path.read_text()
    expected = set(dashboard_agents(agents).keys())
    errors: list[str] = []
    found = re.findall(r"location /([a-z][a-z0-9-]*)/ \{", text)
    if set(found) != expected:
        errors.append(f"dashboard proxy blocks expected {sorted(expected)}, found {sorted(set(found))}")
    for slug in expected:
        if found.count(slug) != 1:
            errors.append(f"expected exactly one location /{slug}/ block, found {found.count(slug)}")
        if text.count(f"location = /{slug} ") != 1:
            errors.append(f"expected one exact redirect block for /{slug}")
    generated = emit_nginx(agents)
    if text != generated:
        diff = "\n".join(difflib.unified_diff(text.splitlines(), generated.splitlines(), "nginx/dashboards.conf", "generated", lineterm=""))
        errors.append("nginx/dashboards.conf is stale; run make generate\n" + diff[:4000])
    if errors:
        raise RegistryError("nginx validation failed:\n" + "\n".join(f"- {e}" for e in errors))


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def validate_discord_bot_mode(agents) -> None:
    """Prevent unsafe Discord bot-to-bot free-chat configuration.

    Team Nexus uses the router/Kanban path for A2A coordination. Allowing all
    bot-authored Discord messages can create loops and waste tokens, so fail
    validation if an agent opts into DISCORD_ALLOW_BOTS=all. Mentions-only mode
    is permitted for narrow smoke tests, but still warned against.
    """
    errors: list[str] = []
    warnings: list[str] = []
    paths = [(".env", ROOT / ".env")]
    for slug in enabled_agents(agents):
        paths.append((f"agents/{slug}/home/.env", ROOT / "agents" / slug / "home" / ".env"))
    for label, path in paths:
        mode = parse_env_file(path).get("DISCORD_ALLOW_BOTS", "").strip().lower()
        if mode == "all":
            errors.append(f"{label}: DISCORD_ALLOW_BOTS=all is not allowed; use the router/Kanban path for A2A coordination")
        elif mode == "mentions":
            warnings.append(f"{label}: DISCORD_ALLOW_BOTS=mentions is permitted only for narrow smoke tests; router/Kanban remains the A2A control plane")
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if errors:
        raise RegistryError("discord bot-mode validation failed:\n" + "\n".join(f"- {e}" for e in errors))


def validate_kanban_assignees(agents) -> None:
    db = ROOT / "shared" / "kanban" / "kanban.db"
    if not db.exists():
        print("warning: shared/kanban/kanban.db not found; skipping kanban assignee validation", file=sys.stderr)
        return
    allowed = set(enabled_agents(agents).keys())
    errors: list[str] = []
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        print(f"warning: cannot open kanban db read-only ({exc}); skipping", file=sys.stderr)
        return
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        closed_statuses = {"done", "closed", "complete", "completed", "archived", "cancelled", "canceled"}
        for table in tables:
            table_q = quote_sqlite_identifier(table)
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table_q})")]
            status_filter = ""
            if "status" in cols:
                placeholders = ",".join("?" for _ in closed_statuses)
                status_q = quote_sqlite_identifier("status")
                status_filter = f" AND ({status_q} IS NULL OR {status_q} NOT IN ({placeholders}))"
            for col in cols:
                if col in ("assignee", "assigned_to"):
                    col_q = quote_sqlite_identifier(col)
                    q = f"SELECT rowid, {col_q} FROM {table_q} WHERE {col_q} IS NOT NULL AND {col_q} != ''{status_filter}"
                    params = list(closed_statuses) if status_filter else []
                    for rowid, assignee in conn.execute(q, params):
                        if assignee not in allowed:
                            errors.append(f"{table} row {rowid}: unknown {col} {assignee!r}")
    finally:
        conn.close()
    if errors:
        raise RegistryError("kanban assignee validation failed:\n" + "\n".join(f"- {e}" for e in errors))


def validate_plugins(_: Any = None) -> None:
    root = ROOT / "shared" / "plugins"
    if not root.exists():
        print("warning: shared/plugins not found; skipping plugin validation", file=sys.stderr)
        return
    errors: list[str] = []
    for plugin in sorted(p for p in root.iterdir() if p.is_dir()):
        if not any(plugin.iterdir()):
            errors.append(f"shared/plugins/{plugin.name} is empty")
            continue
        manifest = plugin / "dashboard" / "manifest.json"
        if not manifest.exists():
            # Allow non-dashboard shared plugin trees only if they contain no dashboard directory.
            if (plugin / "dashboard").exists():
                errors.append(f"shared/plugins/{plugin.name}/dashboard missing manifest.json")
            continue
        try:
            data = json.loads(manifest.read_text())
        except json.JSONDecodeError as exc:
            errors.append(f"{manifest.relative_to(ROOT)} invalid JSON: {exc}")
            continue
        for field in ("name", "version"):
            if not data.get(field):
                errors.append(f"{manifest.relative_to(ROOT)} missing {field}")
        if data.get("entry") and not (manifest.parent / data["entry"]).exists():
            errors.append(f"{manifest.relative_to(ROOT)} entry missing: {data['entry']}")
        if data.get("css") and not (manifest.parent / data["css"]).exists():
            errors.append(f"{manifest.relative_to(ROOT)} css missing: {data['css']}")
    if errors:
        raise RegistryError("plugin validation failed:\n" + "\n".join(f"- {e}" for e in errors))


def validate_all(agents) -> None:
    validate_registry_data(agents)
    validate_filesystem(agents)
    validate_configs(agents)
    validate_compose(agents)
    validate_nginx(agents)
    validate_discord_bot_mode(agents)
    validate_kanban_assignees(agents)
    validate_plugins(agents)
    print("Team Nexus validation OK")


def check_generated_target(path: Path, content: str) -> None:
    if not path.exists():
        raise RegistryError(f"generated file missing: {path.relative_to(ROOT)}")
    if path.read_text() != content:
        diff = "\n".join(difflib.unified_diff(path.read_text().splitlines(), content.splitlines(), str(path.relative_to(ROOT)), "generated", lineterm=""))
        raise RegistryError(f"generated file stale: {path.relative_to(ROOT)}\n{diff[:4000]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    simple_commands = [
        "list-slugs", "list-enabled-slugs", "list-dashboard-slugs", "validate-registry", "next-ports",
        "generate-make", "generate-compose-agents", "generate-compose-dashboards", "generate-nginx", "generate-roster", "validate-filesystem", "validate-configs",
        "validate-compose", "validate-nginx", "validate-discord-bot-mode", "validate-kanban-assignees", "validate-plugins", "validate-all",
    ]
    for command in simple_commands:
        sub.add_parser(command)
    p_add = sub.add_parser("agent-add")
    p_add.add_argument("--slug", required=True)
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--role", required=True)
    p_add.add_argument("--gateway-port", type=int)
    p_add.add_argument("--dashboard-port", type=int)
    p_disable = sub.add_parser("agent-disable")
    p_disable.add_argument("--slug", required=True)
    p_archive = sub.add_parser("agent-archive")
    p_archive.add_argument("--slug", required=True)
    p_archive.add_argument("--force", action="store_true")
    for command in ("agent-add-env", "agent-disable-env", "agent-archive-env"):
        sub.add_parser(command)
    args = parser.parse_args(argv)
    try:
        agents = load_registry()
        if args.command == "list-slugs":
            validate_registry_data(agents); print_list(agents.keys())
        elif args.command == "list-enabled-slugs":
            validate_registry_data(agents); print_list(enabled_agents(agents).keys())
        elif args.command == "list-dashboard-slugs":
            validate_registry_data(agents); print_list(dashboard_agents(agents).keys())
        elif args.command == "validate-registry":
            validate_registry_data(agents); print("registry OK")
        elif args.command == "next-ports":
            validate_registry_data(agents); cmd_next_ports(agents)
        elif args.command == "generate-make":
            validate_registry_data(agents); print(emit_make(agents), end="")
        elif args.command == "generate-compose-agents":
            validate_registry_data(agents); print(emit_compose_agents(agents), end="")
        elif args.command == "generate-compose-dashboards":
            validate_registry_data(agents); print(emit_compose_dashboards(agents), end="")
        elif args.command == "generate-nginx":
            validate_registry_data(agents); print(emit_nginx(agents), end="")
        elif args.command == "generate-roster":
            validate_registry_data(agents); print(emit_roster(agents), end="")
        elif args.command == "validate-filesystem":
            validate_registry_data(agents); validate_filesystem(agents); print("filesystem OK")
        elif args.command == "validate-configs":
            validate_registry_data(agents); validate_configs(agents); print("configs OK")
        elif args.command == "validate-compose":
            validate_registry_data(agents); validate_compose(agents); print("compose OK")
        elif args.command == "validate-nginx":
            validate_registry_data(agents); validate_nginx(agents); print("nginx OK")
        elif args.command == "validate-discord-bot-mode":
            validate_registry_data(agents); validate_discord_bot_mode(agents); print("discord bot mode OK")
        elif args.command == "validate-kanban-assignees":
            validate_registry_data(agents); validate_kanban_assignees(agents); print("kanban assignees OK")
        elif args.command == "validate-plugins":
            validate_plugins(agents); print("plugins OK")
        elif args.command == "validate-all":
            validate_all(agents)
        elif args.command == "agent-add":
            cmd_agent_add(args, agents)
        elif args.command == "agent-add-env":
            cmd_agent_add_env(agents)
        elif args.command == "agent-disable":
            cmd_agent_disable(args, agents)
        elif args.command == "agent-disable-env":
            cmd_agent_disable_env(agents)
        elif args.command == "agent-archive":
            cmd_agent_archive(args, agents)
        elif args.command == "agent-archive-env":
            cmd_agent_archive_env(agents)
        return 0
    except RegistryError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

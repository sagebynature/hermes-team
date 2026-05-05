"""Backend routes for the Agent Identity dashboard plugin.

Exposes a small public identity payload, an optional per-agent profile image, and a
runtime-discovered list of Team Nexus dashboards for the top-banner agent navbar.
In Team Nexus dashboard containers, $HERMES_HOME is /opt/data, so the host file
agents/<agent>/home/profile.jpg is available as /opt/data/profile.jpg.
"""

from __future__ import annotations

import os
import re
import socket
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - dashboard runtime normally has PyYAML
    yaml = None

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter()

ROSTER_PATH = Path("/shared/project/generated/team-roster.md")
DEFAULT_DASHBOARD_PORT = int(os.environ.get("TEAM_NEXUS_DASHBOARD_CONTAINER_PORT", "9119"))
AGENT_SERVICE_RE = re.compile(r"^[-\s]*([a-z0-9][a-z0-9-]*):\s*([^—\n]+?)(?:\s*—\s*(.*))?$")


def _hermes_home() -> Path:
    try:
        from hermes_cli.config import get_hermes_home  # type: ignore

        return Path(get_hermes_home()).expanduser()
    except Exception:
        return Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()


def _profile_path() -> Path:
    return _hermes_home() / "profile.jpg"


def _agent_identity_from_env() -> Dict[str, str]:
    name = os.environ.get("AGENT_NAME") or "Hermes Agent"
    role = os.environ.get("AGENT_ROLE") or ""
    return {
        "name": name,
        "role": role,
        "title": f"{name} Dashboard" if name else "Hermes Dashboard",
    }


def _config_data() -> Dict[str, Any]:
    config_path = _hermes_home() / "config.yaml"
    if not config_path.is_file() or yaml is None:
        return {}
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _dashboard_color_fallback() -> Dict[str, Optional[str]]:
    config_path = _hermes_home() / "config.yaml"
    if not config_path.is_file():
        return {"primary": None, "secondary": None}
    primary: Optional[str] = None
    secondary: Optional[str] = None
    in_dashboard = False
    in_accent_colors = False
    for raw in config_path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("dashboard:"):
            in_dashboard = True
            in_accent_colors = False
            continue
        if in_dashboard and raw and not raw.startswith(" "):
            break
        if not in_dashboard:
            continue
        text = raw.strip()
        if text.startswith("accent_colors:"):
            in_accent_colors = True
            continue
        if text.startswith("primary_color:"):
            primary = text.split(":", 1)[1].strip().strip("'\"")
        elif text.startswith("secondary_color:"):
            secondary = text.split(":", 1)[1].strip().strip("'\"")
        elif in_accent_colors and text.startswith("primary:"):
            primary = text.split(":", 1)[1].strip().strip("'\"")
        elif in_accent_colors and text.startswith("secondary:"):
            secondary = text.split(":", 1)[1].strip().strip("'\"")
    return {"primary": _normalize_hex(primary), "secondary": _normalize_hex(secondary)}


def _normalize_hex(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return text.lower()
    if re.fullmatch(r"[0-9a-fA-F]{6}", text):
        return f"#{text.lower()}"
    return None


def _dashboard_colors() -> Dict[str, Optional[str]]:
    config = _config_data()
    dashboard = config.get("dashboard") if isinstance(config.get("dashboard"), dict) else {}
    accent_colors = dashboard.get("accent_colors") if isinstance(dashboard.get("accent_colors"), dict) else {}
    fallback = _dashboard_color_fallback()
    primary = (
        _normalize_hex(accent_colors.get("primary"))
        or _normalize_hex(dashboard.get("primary_color"))
        or fallback.get("primary")
        or _normalize_hex(os.environ.get("DASHBOARD_PRIMARY_COLOR"))
    )
    secondary = (
        _normalize_hex(accent_colors.get("secondary"))
        or _normalize_hex(dashboard.get("secondary_color"))
        or fallback.get("secondary")
        or _normalize_hex(os.environ.get("DASHBOARD_SECONDARY_COLOR"))
    )
    return {"primary": primary, "secondary": secondary}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "agent"


def _current_slug() -> str:
    explicit = os.environ.get("AGENT_SLUG") or os.environ.get("TEAM_NEXUS_AGENT")
    if explicit:
        return _slugify(explicit)
    return _slugify(os.environ.get("AGENT_NAME") or "agent")


def _parse_roster() -> List[Dict[str, str]]:
    agents: List[Dict[str, str]] = []
    if ROSTER_PATH.is_file():
        for line in ROSTER_PATH.read_text(encoding="utf-8").splitlines():
            match = AGENT_SERVICE_RE.match(line.strip())
            if not match:
                continue
            slug, name, role = match.groups()
            agents.append(
                {
                    "slug": slug.strip(),
                    "name": name.strip(),
                    "role": (role or "").strip(),
                }
            )
    if not agents:
        identity = _agent_identity_from_env()
        agents.append({"slug": _current_slug(), "name": identity["name"], "role": identity["role"]})
    return agents


def _dashboard_service_url(slug: str) -> str:
    return f"http://{slug}-dashboard:{DEFAULT_DASHBOARD_PORT}"


def _dashboard_is_running(slug: str) -> bool:
    try:
        with urllib.request.urlopen(f"{_dashboard_service_url(slug)}/api/config", timeout=0.35) as response:
            return 200 <= response.status < 500
    except urllib.error.HTTPError as exc:
        # Hermes may protect /api/config with auth and return 401. Any HTTP
        # response from the peer dashboard still proves the service is running.
        return 200 <= exc.code < 500
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
        return False


def _browser_href(slug: str, request: Optional[Request]) -> str:
    # If this request came through the Team Nexus nginx reverse proxy, sibling
    # dashboards live under /<agent> on the same origin. This is the normal web
    # dashboard path and keeps links portable across localhost ports/domains.
    if request and request.headers.get("x-forwarded-prefix"):
        return f"/{slug}/sessions"

    # Direct dashboard ports cannot route /<other-agent>/... themselves, so fall
    # back to the conventional Team Nexus reverse-proxy port when known.
    nginx_port = os.environ.get("NGINX_PORT") or "9130"
    return f"http://127.0.0.1:{nginx_port}/{slug}/sessions"


@router.get("/identity")
async def identity() -> Dict[str, Any]:
    profile = _profile_path()
    has_profile = profile.is_file()
    return {
        "ok": True,
        "slug": _current_slug(),
        **_agent_identity_from_env(),
        "profile_image": {
            "available": has_profile,
            "url": "/api/plugins/agent-identity-dashboard/profile.jpg" if has_profile else None,
        },
        "dashboard_colors": _dashboard_colors(),
    }


@router.get("/agents")
async def agents(request: Request) -> Dict[str, Any]:
    current_slug = _current_slug()
    running_agents = []
    for agent in _parse_roster():
        slug = agent["slug"]
        if slug != current_slug and not _dashboard_is_running(slug):
            continue
        running_agents.append(
            {
                **agent,
                "current": slug == current_slug,
                "href": _browser_href(slug, request),
            }
        )
    return {"ok": True, "current_slug": current_slug, "agents": running_agents}


@router.get("/profile.jpg")
async def profile_image() -> FileResponse:
    profile = _profile_path()
    if not profile.is_file():
        raise HTTPException(status_code=404, detail="profile.jpg not found in Hermes home")
    return FileResponse(
        profile,
        media_type="image/jpeg",
        filename="profile.jpg",
        headers={"Cache-Control": "public, max-age=60"},
    )

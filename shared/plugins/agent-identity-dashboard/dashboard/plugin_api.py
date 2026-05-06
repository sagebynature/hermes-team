"""Backend routes for the Agent Identity dashboard plugin.

Exposes a small public identity payload, an optional profile image, and the
profile-driven Team Nexus roster for the top-banner profile navbar.
In Team Nexus dashboard containers, $HERMES_HOME points at the active rendered
profile under /opt/data/profiles/<profile>; profile.jpg is optional.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - dashboard runtime normally has PyYAML
    yaml = None

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter()

_DEFAULT_PROFILE_SPEC = Path("/workspace/profiles/team-nexus.profiles.yaml")
if not _DEFAULT_PROFILE_SPEC.is_file():
    _DEFAULT_PROFILE_SPEC = Path.cwd() / "profiles" / "team-nexus.profiles.yaml"
PROFILE_SPEC_PATH = Path(os.environ.get("TEAM_NEXUS_PROFILE_SPEC", str(_DEFAULT_PROFILE_SPEC)))


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


def _fallback_parse_profile_spec(text: str) -> List[Dict[str, str]]:
    """Small no-dependency parser for the simple profile spec shape."""
    agents: List[Dict[str, str]] = []
    in_profiles = False
    current_slug: Optional[str] = None
    current: Dict[str, str] = {}
    for raw in text.splitlines():
        if raw.startswith("profiles:"):
            in_profiles = True
            continue
        if in_profiles and raw and not raw.startswith(" "):
            break
        if not in_profiles:
            continue
        profile_match = re.match(r"^  ([a-z0-9_-]+):\s*$", raw)
        if profile_match:
            if current_slug and current.get("status") == "active_v1":
                agents.append(
                    {
                        "slug": current_slug,
                        "name": current.get("display_name", current_slug.title()),
                        "role": current.get("one_job", ""),
                    }
                )
            current_slug = profile_match.group(1)
            current = {}
            continue
        field_match = re.match(r"^    (status|display_name|one_job):\s*(.+?)\s*$", raw)
        if field_match and current_slug:
            current[field_match.group(1)] = field_match.group(2).strip().strip("'\"")
    if current_slug and current.get("status") == "active_v1":
        agents.append(
            {
                "slug": current_slug,
                "name": current.get("display_name", current_slug.title()),
                "role": current.get("one_job", ""),
            }
        )
    return agents


def _parse_profile_roster() -> List[Dict[str, str]]:
    agents: List[Dict[str, str]] = []
    if PROFILE_SPEC_PATH.is_file():
        text = PROFILE_SPEC_PATH.read_text(encoding="utf-8")
        if yaml is not None:
            try:
                data = yaml.safe_load(text) or {}
                profiles = data.get("profiles") if isinstance(data.get("profiles"), dict) else {}
                for slug, spec in profiles.items():
                    if not isinstance(spec, dict) or spec.get("status") != "active_v1":
                        continue
                    agents.append(
                        {
                            "slug": str(slug),
                            "name": str(spec.get("display_name") or str(slug).title()),
                            "role": str(spec.get("one_job") or spec.get("summary") or ""),
                        }
                    )
            except Exception:
                agents = []
        if not agents:
            agents = _fallback_parse_profile_spec(text)
    if not agents:
        identity = _agent_identity_from_env()
        agents.append({"slug": _current_slug(), "name": identity["name"], "role": identity["role"]})
    return agents


def _browser_href(slug: str, request: Optional[Request]) -> str:
    if slug == _current_slug():
        return "/sessions"
    return f"#profile-{slug}"


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
    profile_agents = []
    for agent in _parse_profile_roster():
        slug = agent["slug"]
        profile_agents.append(
            {
                **agent,
                "current": slug == current_slug,
                "href": _browser_href(slug, request),
            }
        )
    return {"ok": True, "current_slug": current_slug, "agents": profile_agents}


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

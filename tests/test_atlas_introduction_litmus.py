from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ATLAS_AGENTS = REPO_ROOT / "agents" / "atlas" / "home" / "AGENTS.md"
ATLAS_SOUL = REPO_ROOT / "agents" / "atlas" / "home" / "SOUL.md"
ATLAS_CONFIG = REPO_ROOT / "agents" / "atlas" / "home" / "config.yaml"
TEAM_NEXUS_ENTRYPOINT = REPO_ROOT / "docker" / "team-nexus-entrypoint.sh"


def test_atlas_treats_multi_agent_introduction_as_durable_dispatch():
    agents_text = ATLAS_AGENTS.read_text(encoding="utf-8")
    soul_text = ATLAS_SOUL.read_text(encoding="utf-8")

    assert "Team Introduction Litmus Test" in agents_text
    assert "Do not merely write a theatrical summons in Discord" in agents_text
    assert "Vega, Scout, Forge, Lumen, Blitz, Ledger, and Sentinel" in agents_text
    assert "role, primary expertise, and what they bring to Team Nexus" in agents_text
    assert "that is execution approval" in soul_text
    assert "Never write first-person content pretending to be Vega, Scout, Forge, Lumen, Blitz, Ledger, or Sentinel" in agents_text


def test_atlas_discord_mentions_are_not_claimed_as_dispatch():
    agents_text = ATLAS_AGENTS.read_text(encoding="utf-8")
    assert "A visible `@Vega @Forge ...` post is not durable dispatch unless router/Kanban work is also created" in agents_text
    assert "reply with the conversation ID and message IDs" in agents_text


def test_atlas_gateway_cannot_directly_create_kanban_fanout_tasks():
    config_text = ATLAS_CONFIG.read_text(encoding="utf-8")
    agents_text = ATLAS_AGENTS.read_text(encoding="utf-8")

    assert "toolsets:\n- hermes-cli\nagent:" in config_text
    assert "disabled_toolsets:\n  - code_execution\n  - delegation\n  - messaging\n  - skills" in config_text
    assert "not Discord mentions, direct `kanban_create` calls, `delegate_task`, or generic Kanban-orchestrator role names" in agents_text
    assert "Do not use `delegate_task` for Team Nexus fanout" in agents_text
    assert "/shared/scripts/team-message-router.py send" in agents_text


def test_atlas_entrypoint_blocks_direct_hermes_kanban_create_escape_hatch():
    entrypoint = TEAM_NEXUS_ENTRYPOINT.read_text(encoding="utf-8")

    assert '${AGENT_NAME:-}' in entrypoint
    assert '"Atlas"' in entrypoint
    assert '"${1:-}" = "kanban"' in entrypoint
    assert '"${2:-}" = "create"' in entrypoint
    assert 'TEAM_NEXUS_ROUTER_DISPATCH:-' in entrypoint
    assert "Atlas may not create Kanban tasks directly" in entrypoint
    assert "/shared/scripts/team-message-router.py send" in entrypoint

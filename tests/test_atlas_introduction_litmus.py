from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ATLAS_AGENTS = REPO_ROOT / "agents" / "atlas" / "home" / "AGENTS.md"
ATLAS_SOUL = REPO_ROOT / "agents" / "atlas" / "home" / "SOUL.md"


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
    assert "reply with the task/message IDs" in agents_text

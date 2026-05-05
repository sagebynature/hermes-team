from collections import OrderedDict
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "team_registry.py"
spec = importlib.util.spec_from_file_location("team_registry", MODULE_PATH)
team_registry = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(team_registry)


def fake_agents():
    return OrderedDict([
        ("atlas", {"enabled": True}),
        ("forge", {"enabled": True}),
    ])


def write_env(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_validate_discord_bot_mode_rejects_all(tmp_path, monkeypatch):
    monkeypatch.setattr(team_registry, "ROOT", tmp_path)
    write_env(tmp_path, "agents/atlas/home/.env", "DISCORD_ALLOW_BOTS=all\n")

    try:
        team_registry.validate_discord_bot_mode(fake_agents())
    except team_registry.RegistryError as exc:
        assert "DISCORD_ALLOW_BOTS=all is not allowed" in str(exc)
    else:
        raise AssertionError("expected RegistryError")


def test_validate_discord_bot_mode_allows_absent_and_mentions_warns(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(team_registry, "ROOT", tmp_path)
    write_env(tmp_path, "agents/forge/home/.env", "DISCORD_ALLOW_BOTS=mentions\n")

    team_registry.validate_discord_bot_mode(fake_agents())

    captured = capsys.readouterr()
    assert "mentions is permitted only for narrow smoke tests" in captured.err

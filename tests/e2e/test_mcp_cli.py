"""End-to-end test for MCP fragment roundtrip via the CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.add import add
from ai_dotfiles.commands.remove import remove
from ai_dotfiles.core.mcp_ownership import OWNERSHIP_FILENAME


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    return home_dir


@pytest.fixture
def storage(home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    storage_dir = home / ".ai-dotfiles"
    storage_dir.mkdir()
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage_dir))
    return storage_dir


@pytest.fixture
def catalog(storage: Path) -> Path:
    cat = storage / "catalog"
    cat.mkdir()
    domain = cat / "mcptest"
    domain.mkdir()
    (domain / "domain.json").write_text(
        json.dumps({"name": "mcptest", "description": "End-to-end MCP test"}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (domain / "mcp.fragment.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "mcptest-server": {
                        "command": "echo",
                        "args": ["hi"],
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return cat


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".git").mkdir()
    monkeypatch.chdir(proj)
    return proj


def test_add_then_remove_roundtrip_mcp(catalog: Path, project: Path) -> None:
    runner = CliRunner()

    # 1. add
    add_result = runner.invoke(add, ["@mcptest"])
    assert add_result.exit_code == 0, add_result.output

    mcp = json.loads((project / ".mcp.json").read_text(encoding="utf-8"))
    assert "mcptest-server" in mcp["mcpServers"]

    settings = json.loads(
        (project / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert "mcp__mcptest-server__*" in settings["permissions"]["allow"]
    assert settings["enabledMcpjsonServers"] == ["mcptest-server"]

    ownership = json.loads(
        (project / ".claude" / OWNERSHIP_FILENAME).read_text(encoding="utf-8")
    )
    assert ownership == {"mcptest-server": ["mcptest"]}

    # 2. remove
    remove_result = runner.invoke(remove, ["@mcptest"])
    assert remove_result.exit_code == 0, remove_result.output

    assert not (project / ".mcp.json").exists()
    assert not (project / ".claude" / OWNERSHIP_FILENAME).exists()

    # settings.json may still exist for non-MCP reasons, but should not
    # contain MCP traces.
    settings_path = project / ".claude" / "settings.json"
    if settings_path.exists():
        remaining = json.loads(settings_path.read_text(encoding="utf-8"))
        allow = remaining.get("permissions", {}).get("allow", [])
        assert "mcp__mcptest-server__*" not in allow
        assert "mcptest-server" not in remaining.get("enabledMcpjsonServers", [])

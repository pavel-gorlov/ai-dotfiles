"""Integration tests for MCP fragment handling in add / remove."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.add import add
from ai_dotfiles.commands.remove import remove
from ai_dotfiles.core.mcp_ownership import OWNERSHIP_FILENAME

pytestmark = pytest.mark.integration


# ── Fixtures ────────────────────────────────────────────────────────────────


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
    return cat


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".git").mkdir()
    monkeypatch.chdir(proj)
    return proj


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _seed_mcp_domain(
    catalog: Path,
    name: str = "mcptest",
    servers: dict[str, dict[str, Any]] | None = None,
    requires_npm: list[str] | None = None,
) -> Path:
    """Create ``catalog/<name>/`` with an ``mcp.fragment.json``."""
    domain = catalog / name
    domain.mkdir(parents=True)
    if servers is None:
        servers = {
            f"{name}-server": {
                "command": "echo",
                "args": ["hi"],
            }
        }
    fragment: dict[str, Any] = {
        "_domain": name,
        "_description": f"{name} domain",
        "mcpServers": servers,
    }
    if requires_npm is not None:
        fragment["_requires"] = {"npm": requires_npm}
    (domain / "mcp.fragment.json").write_text(
        json.dumps(fragment, indent=2) + "\n",
        encoding="utf-8",
    )
    return domain


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ── add: MCP writes ─────────────────────────────────────────────────────────


def test_add_writes_mcp_json(runner: CliRunner, catalog: Path, project: Path) -> None:
    _seed_mcp_domain(catalog)

    result = runner.invoke(add, ["@mcptest"])
    assert result.exit_code == 0, result.output

    mcp = _read_json(project / ".mcp.json")
    assert mcp["mcpServers"]["mcptest-server"] == {
        "command": "echo",
        "args": ["hi"],
    }


def test_add_injects_mcp_permissions_into_settings(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    _seed_mcp_domain(catalog)

    result = runner.invoke(add, ["@mcptest"])
    assert result.exit_code == 0

    settings = _read_json(project / ".claude" / "settings.json")
    assert "mcp__mcptest-server__*" in settings["permissions"]["allow"]


def test_add_populates_enabled_mcpjson_servers_with_domain_owned_only(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    _seed_mcp_domain(catalog)

    result = runner.invoke(add, ["@mcptest"])
    assert result.exit_code == 0

    settings = _read_json(project / ".claude" / "settings.json")
    assert settings["enabledMcpjsonServers"] == ["mcptest-server"]


def test_add_preserves_user_entries_in_enabled_mcpjson_servers(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    # Seed user-authored settings.json with a pre-existing allowlist entry.
    (project / ".claude").mkdir()
    (project / ".claude" / "settings.json").write_text(
        json.dumps({"enabledMcpjsonServers": ["user-entry"]}) + "\n"
    )

    _seed_mcp_domain(catalog)
    result = runner.invoke(add, ["@mcptest"])
    assert result.exit_code == 0, result.output

    settings = _read_json(project / ".claude" / "settings.json")
    assert "user-entry" in settings["enabledMcpjsonServers"]
    assert "mcptest-server" in settings["enabledMcpjsonServers"]


def test_add_preserves_user_authored_mcp_server(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    (project / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"user-srv": {"command": "user-cmd"}}}) + "\n",
        encoding="utf-8",
    )

    _seed_mcp_domain(catalog)
    result = runner.invoke(add, ["@mcptest"])
    assert result.exit_code == 0, result.output

    mcp = _read_json(project / ".mcp.json")
    assert mcp["mcpServers"]["user-srv"] == {"command": "user-cmd"}
    assert "mcptest-server" in mcp["mcpServers"]

    ownership = _read_json(project / ".claude" / OWNERSHIP_FILENAME)
    assert ownership == {"mcptest-server": ["mcptest"]}


def test_add_backs_up_pre_existing_mcp_json(
    runner: CliRunner, catalog: Path, project: Path, home: Path
) -> None:
    (project / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"user-srv": {"command": "u"}}}) + "\n",
        encoding="utf-8",
    )

    _seed_mcp_domain(catalog)
    result = runner.invoke(add, ["@mcptest"])
    assert result.exit_code == 0, result.output

    backup_root = home / ".dotfiles-backup" / ".claude-mcp" / project.name
    assert backup_root.exists()
    backups = list(backup_root.iterdir())
    assert len(backups) >= 1


def test_add_writes_ownership_file(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    _seed_mcp_domain(catalog)
    result = runner.invoke(add, ["@mcptest"])
    assert result.exit_code == 0

    ownership = _read_json(project / ".claude" / OWNERSHIP_FILENAME)
    assert ownership == {"mcptest-server": ["mcptest"]}


def test_two_domains_declare_same_server_ownership_records_both(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    _seed_mcp_domain(
        catalog,
        name="alpha",
        servers={"shared": {"command": "alpha-version"}},
    )
    _seed_mcp_domain(
        catalog,
        name="beta",
        servers={"shared": {"command": "beta-version"}},
    )

    result = runner.invoke(add, ["@alpha", "@beta"])
    assert result.exit_code == 0, result.output

    ownership = _read_json(project / ".claude" / OWNERSHIP_FILENAME)
    assert ownership == {"shared": ["alpha", "beta"]}

    mcp = _read_json(project / ".mcp.json")
    # Later domain wins on conflict.
    assert mcp["mcpServers"]["shared"] == {"command": "beta-version"}


def test_add_first_time_collision_user_wins(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    (project / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"shared": {"command": "user-keeps-this"}}}) + "\n",
        encoding="utf-8",
    )

    _seed_mcp_domain(catalog, servers={"shared": {"command": "domain-version"}})
    result = runner.invoke(add, ["@mcptest"])
    assert result.exit_code == 0

    mcp = _read_json(project / ".mcp.json")
    assert mcp["mcpServers"]["shared"] == {"command": "user-keeps-this"}


# ── remove: MCP cleanup ─────────────────────────────────────────────────────


def test_remove_strips_only_domain_servers(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    # Seed a user server + add a domain; then remove the domain.
    (project / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"user-srv": {"command": "u"}}}) + "\n",
        encoding="utf-8",
    )
    _seed_mcp_domain(catalog)

    runner.invoke(add, ["@mcptest"])
    result = runner.invoke(remove, ["@mcptest"])
    assert result.exit_code == 0, result.output

    mcp = _read_json(project / ".mcp.json")
    assert "mcptest-server" not in mcp["mcpServers"]
    assert mcp["mcpServers"]["user-srv"] == {"command": "u"}


def test_remove_deletes_mcp_json_when_last_domain_gone_and_no_user_servers(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    _seed_mcp_domain(catalog)

    runner.invoke(add, ["@mcptest"])
    result = runner.invoke(remove, ["@mcptest"])
    assert result.exit_code == 0

    assert not (project / ".mcp.json").exists()
    assert not (project / ".claude" / OWNERSHIP_FILENAME).exists()


def test_remove_keeps_mcp_json_with_only_user_servers_remaining(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    (project / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"user-srv": {"command": "u"}}}) + "\n",
        encoding="utf-8",
    )
    _seed_mcp_domain(catalog)

    runner.invoke(add, ["@mcptest"])
    runner.invoke(remove, ["@mcptest"])

    assert (project / ".mcp.json").exists()
    mcp = _read_json(project / ".mcp.json")
    assert mcp["mcpServers"] == {"user-srv": {"command": "u"}}


def test_remove_removes_mcp_permissions_from_settings(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    _seed_mcp_domain(catalog)

    runner.invoke(add, ["@mcptest"])
    runner.invoke(remove, ["@mcptest"])

    settings_path = project / ".claude" / "settings.json"
    if settings_path.exists():
        settings = _read_json(settings_path)
        perms = settings.get("permissions", {}).get("allow", [])
        assert "mcp__mcptest-server__*" not in perms


def test_remove_drops_own_entries_from_enabled_mcpjson_servers(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    _seed_mcp_domain(catalog)

    runner.invoke(add, ["@mcptest"])
    runner.invoke(remove, ["@mcptest"])

    settings_path = project / ".claude" / "settings.json"
    if settings_path.exists():
        settings = _read_json(settings_path)
        assert "mcptest-server" not in settings.get("enabledMcpjsonServers", [])


def test_remove_keeps_user_entries_in_enabled_mcpjson_servers(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    (project / ".claude").mkdir()
    (project / ".claude" / "settings.json").write_text(
        json.dumps({"enabledMcpjsonServers": ["user-entry"]}) + "\n"
    )
    _seed_mcp_domain(catalog)

    runner.invoke(add, ["@mcptest"])
    runner.invoke(remove, ["@mcptest"])

    settings_path = project / ".claude" / "settings.json"
    assert settings_path.exists()
    settings = _read_json(settings_path)
    assert "user-entry" in settings.get("enabledMcpjsonServers", [])


def test_remove_deletes_ownership_file_when_empty(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    _seed_mcp_domain(catalog)

    runner.invoke(add, ["@mcptest"])
    runner.invoke(remove, ["@mcptest"])

    assert not (project / ".claude" / OWNERSHIP_FILENAME).exists()


# ── warnings ────────────────────────────────────────────────────────────────


def test_env_var_unset_emits_warning(
    runner: CliRunner,
    catalog: Path,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MCPTEST_TOKEN", raising=False)
    _seed_mcp_domain(
        catalog,
        servers={
            "mcptest-server": {
                "command": "echo",
                "env": {"TOKEN": "${MCPTEST_TOKEN}"},
            }
        },
    )

    result = runner.invoke(add, ["@mcptest"])
    assert result.exit_code == 0
    assert "MCPTEST_TOKEN" in result.output


def test_env_var_with_default_suppresses_warning(
    runner: CliRunner,
    catalog: Path,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MCPTEST_TOKEN", raising=False)
    _seed_mcp_domain(
        catalog,
        servers={
            "mcptest-server": {
                "command": "echo",
                "env": {"TOKEN": "${MCPTEST_TOKEN:-fallback}"},
            }
        },
    )

    result = runner.invoke(add, ["@mcptest"])
    assert result.exit_code == 0
    assert "MCPTEST_TOKEN" not in result.output


def test_requires_npm_missing_emits_warning(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    (project / "package.json").write_text(
        json.dumps({"devDependencies": {"other": "1.0"}}) + "\n"
    )
    _seed_mcp_domain(catalog, requires_npm=["@foo/bar"])

    result = runner.invoke(add, ["@mcptest"])
    assert result.exit_code == 0
    assert "@foo/bar" in result.output
    assert "npm install -D @foo/bar" in result.output


def test_requires_npm_present_silent(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    (project / "package.json").write_text(
        json.dumps({"devDependencies": {"@foo/bar": "1.0"}}) + "\n"
    )
    _seed_mcp_domain(catalog, requires_npm=["@foo/bar"])

    result = runner.invoke(add, ["@mcptest"])
    assert result.exit_code == 0
    assert "@foo/bar" not in result.output


def test_requires_npm_no_package_json_silent(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    _seed_mcp_domain(catalog, requires_npm=["@foo/bar"])

    result = runner.invoke(add, ["@mcptest"])
    assert result.exit_code == 0
    # No package.json -> no warning about missing deps.
    assert "@foo/bar" not in result.output


# ── safety ──────────────────────────────────────────────────────────────────


def test_symlinks_never_include_mcp_fragment_json(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    # Build a fully-featured domain: skill + agent + mcp fragment.
    _seed_mcp_domain(catalog, name="mixed")
    (catalog / "mixed" / "skills" / "a-skill").mkdir(parents=True)
    (catalog / "mixed" / "skills" / "a-skill" / "SKILL.md").write_text("x")

    result = runner.invoke(add, ["@mixed"])
    assert result.exit_code == 0, result.output

    claude_dir = project / ".claude"
    for entry in claude_dir.rglob("*"):
        if entry.is_symlink():
            assert entry.name != "mcp.fragment.json"

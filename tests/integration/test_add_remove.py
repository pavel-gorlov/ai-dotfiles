"""Integration tests for ``ai-dotfiles add`` and ``remove``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.add import add
from ai_dotfiles.commands.remove import remove
from ai_dotfiles.core import manifest

pytestmark = pytest.mark.integration


# ── Fixtures ──────────────────────────────────────────────────────────────


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
    """Populate catalog with a domain and a standalone skill."""
    cat = storage / "catalog"

    # Domain `testdomain` with skill, agent, settings fragment.
    domain = cat / "testdomain"
    (domain / "skills" / "test-skill").mkdir(parents=True)
    (domain / "skills" / "test-skill" / "SKILL.md").write_text("test skill\n")
    (domain / "agents").mkdir()
    (domain / "agents" / "test-agent.md").write_text("# agent\n")
    (domain / "settings.fragment.json").write_text(
        json.dumps(
            {
                "_domain": "testdomain",
                "hooks": {"PostToolUse": [{"matcher": "Write", "hooks": []}]},
                "permissions": {"allow": ["Read"]},
            }
        )
    )

    # Standalone skill.
    (cat / "skills" / "test-standalone").mkdir(parents=True)
    (cat / "skills" / "test-standalone" / "SKILL.md").write_text("standalone\n")

    # Standalone agent (for a multi-add test).
    (cat / "agents").mkdir(exist_ok=True)
    (cat / "agents" / "test-agent-solo.md").write_text("# solo\n")

    return cat


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a project with .git and chdir into it."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".git").mkdir()
    monkeypatch.chdir(proj)
    return proj


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ── add: project ──────────────────────────────────────────────────────────


def test_add_project_domain(runner: CliRunner, catalog: Path, project: Path) -> None:
    result = runner.invoke(add, ["@testdomain"])
    assert result.exit_code == 0, result.output

    # Manifest updated.
    pkgs = manifest.get_packages(project / "ai-dotfiles.json")
    assert pkgs == ["@testdomain"]

    # Symlinks created under project .claude/.
    claude = project / ".claude"
    assert (claude / "skills" / "test-skill").is_symlink()
    assert (claude / "agents" / "test-agent.md").is_symlink()


def test_add_project_standalone(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    result = runner.invoke(add, ["skill:test-standalone"])
    assert result.exit_code == 0, result.output

    pkgs = manifest.get_packages(project / "ai-dotfiles.json")
    assert pkgs == ["skill:test-standalone"]
    assert (project / ".claude" / "skills" / "test-standalone").is_symlink()


def test_add_project_multiple(runner: CliRunner, catalog: Path, project: Path) -> None:
    result = runner.invoke(
        add, ["@testdomain", "skill:test-standalone", "agent:test-agent-solo"]
    )
    assert result.exit_code == 0, result.output

    pkgs = manifest.get_packages(project / "ai-dotfiles.json")
    assert pkgs == ["@testdomain", "skill:test-standalone", "agent:test-agent-solo"]

    claude = project / ".claude"
    assert (claude / "skills" / "test-skill").is_symlink()
    assert (claude / "skills" / "test-standalone").is_symlink()
    assert (claude / "agents" / "test-agent-solo.md").is_symlink()


def test_add_project_duplicate(runner: CliRunner, catalog: Path, project: Path) -> None:
    runner.invoke(add, ["@testdomain"])
    result = runner.invoke(add, ["@testdomain"])
    assert result.exit_code == 0, result.output
    assert "already installed" in result.output.lower()

    # Manifest still has exactly one entry.
    pkgs = manifest.get_packages(project / "ai-dotfiles.json")
    assert pkgs == ["@testdomain"]


def test_add_project_rebuilds_settings(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    result = runner.invoke(add, ["@testdomain"])
    assert result.exit_code == 0, result.output

    settings_path = project / ".claude" / "settings.json"
    assert settings_path.is_file()
    data = json.loads(settings_path.read_text())
    assert "_domain" not in data  # meta stripped
    assert "permissions" in data
    assert "hooks" in data


def test_add_project_missing_package(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    result = runner.invoke(add, ["skill:does-not-exist"])
    assert result.exit_code != 0
    # Manifest not written.
    assert not (project / "ai-dotfiles.json").exists()
    out = result.output.lower()
    assert "not found" in out or "does not exist" in out


# ── add: global ───────────────────────────────────────────────────────────


def test_add_global(
    runner: CliRunner, catalog: Path, storage: Path, home: Path
) -> None:
    result = runner.invoke(add, ["-g", "@testdomain"])
    assert result.exit_code == 0, result.output

    global_manifest = storage / "global.json"
    assert global_manifest.is_file()
    assert manifest.get_packages(global_manifest) == ["@testdomain"]

    claude_home = home / ".claude"
    assert (claude_home / "skills" / "test-skill").is_symlink()
    assert (claude_home / "agents" / "test-agent.md").is_symlink()
    assert (claude_home / "settings.json").is_file()


# ── remove: project ──────────────────────────────────────────────────────


def test_remove_project(runner: CliRunner, catalog: Path, project: Path) -> None:
    runner.invoke(add, ["@testdomain"])
    claude = project / ".claude"
    assert (claude / "skills" / "test-skill").is_symlink()

    result = runner.invoke(remove, ["@testdomain"])
    assert result.exit_code == 0, result.output

    assert manifest.get_packages(project / "ai-dotfiles.json") == []
    assert not (claude / "skills" / "test-skill").exists()
    assert not (claude / "agents" / "test-agent.md").exists()


def test_remove_project_multiple(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    runner.invoke(add, ["@testdomain", "skill:test-standalone"])
    result = runner.invoke(remove, ["@testdomain", "skill:test-standalone"])
    assert result.exit_code == 0, result.output

    assert manifest.get_packages(project / "ai-dotfiles.json") == []
    claude = project / ".claude"
    assert not (claude / "skills" / "test-skill").exists()
    assert not (claude / "skills" / "test-standalone").exists()


def test_remove_project_not_installed(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    # Create an empty manifest by touching the project root.
    (project / "ai-dotfiles.json").write_text('{"packages": []}\n')

    result = runner.invoke(remove, ["@testdomain"])
    assert result.exit_code == 0, result.output
    assert "none of these packages" in (result.output + result.stderr).lower()


def test_remove_project_rebuilds_settings(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    runner.invoke(add, ["@testdomain"])
    settings_path = project / ".claude" / "settings.json"
    assert settings_path.is_file()

    result = runner.invoke(remove, ["@testdomain"])
    assert result.exit_code == 0, result.output

    # No domain fragments left -> settings.json removed.
    assert not settings_path.exists()


# ── remove: global ────────────────────────────────────────────────────────


def test_remove_global(
    runner: CliRunner, catalog: Path, storage: Path, home: Path
) -> None:
    runner.invoke(add, ["-g", "@testdomain"])
    claude_home = home / ".claude"
    assert (claude_home / "skills" / "test-skill").is_symlink()

    result = runner.invoke(remove, ["-g", "@testdomain"])
    assert result.exit_code == 0, result.output

    assert manifest.get_packages(storage / "global.json") == []
    assert not (claude_home / "skills" / "test-skill").exists()
    assert not (claude_home / "agents" / "test-agent.md").exists()


# ── roundtrip ─────────────────────────────────────────────────────────────


def test_add_then_remove_roundtrip(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    claude = project / ".claude"

    add_result = runner.invoke(add, ["@testdomain", "skill:test-standalone"])
    assert add_result.exit_code == 0, add_result.output
    assert (claude / "skills" / "test-skill").is_symlink()
    assert (claude / "skills" / "test-standalone").is_symlink()
    assert (claude / "agents" / "test-agent.md").is_symlink()
    assert (claude / "settings.json").is_file()

    rm_result = runner.invoke(remove, ["@testdomain", "skill:test-standalone"])
    assert rm_result.exit_code == 0, rm_result.output

    assert manifest.get_packages(project / "ai-dotfiles.json") == []
    # All catalog-owned symlinks gone.
    assert not (claude / "skills" / "test-skill").exists()
    assert not (claude / "skills" / "test-standalone").exists()
    assert not (claude / "agents" / "test-agent.md").exists()
    assert not (claude / "settings.json").exists()

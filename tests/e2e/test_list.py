"""E2E tests for ``ai-dotfiles list``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.list_cmd import list_cmd

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
    (storage_dir / "catalog").mkdir()
    return storage_dir


@pytest.fixture
def project(home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    proj = home / "proj"
    proj.mkdir()
    (proj / ".git").mkdir()
    monkeypatch.chdir(proj)
    return proj


def _write_manifest(path: Path, packages: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"packages": packages}, indent=2) + "\n")


# ── list (project) ────────────────────────────────────────────────────────


def test_list_project_with_packages(storage: Path, project: Path) -> None:
    _write_manifest(
        project / "ai-dotfiles.json",
        [
            "@python",
            "@telegram-api",
            "skill:code-review",
            "skill:git-workflow",
            "agent:researcher",
            "rule:security",
        ],
    )

    result = CliRunner().invoke(list_cmd, [])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "Project (ai-dotfiles.json):" in out
    assert "Global" in out  # header appears even when global.json is missing
    assert "Domains:" in out
    assert "@python" in out
    assert "@telegram-api" in out
    assert "Skills:" in out
    assert "skill:code-review" in out
    assert "skill:git-workflow" in out
    assert "Agents:" in out
    assert "agent:researcher" in out
    assert "Rules:" in out
    assert "rule:security" in out


def test_list_shows_project_and_global(storage: Path, project: Path) -> None:
    _write_manifest(project / "ai-dotfiles.json", ["@python", "skill:code-review"])
    _write_manifest(storage / "global.json", ["@devops", "agent:researcher"])

    result = CliRunner().invoke(list_cmd, [])

    assert result.exit_code == 0, result.output
    out = result.output
    # Both scope headers present
    assert "Project (ai-dotfiles.json):" in out
    assert "Global (global.json):" in out
    # Project content
    assert "@python" in out
    assert "skill:code-review" in out
    # Global content
    assert "@devops" in out
    assert "agent:researcher" in out
    # Project block comes before Global
    assert out.index("Project") < out.index("Global")


def test_list_project_empty(storage: Path, project: Path) -> None:
    _write_manifest(project / "ai-dotfiles.json", [])

    result = CliRunner().invoke(list_cmd, [])

    assert result.exit_code == 0, result.output
    # Project section prints the empty note (and Global note since it's missing too)
    assert "No packages installed." in result.output


def test_list_project_missing_manifest_still_shows_global(
    storage: Path, project: Path
) -> None:
    """No project manifest → friendly note, no error; global section still shown."""
    _write_manifest(storage / "global.json", ["skill:code-review"])

    result = CliRunner().invoke(list_cmd, [])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "Project:" in out
    assert "No ai-dotfiles.json" in out
    assert "Global (global.json):" in out
    assert "skill:code-review" in out


# ── list -g ───────────────────────────────────────────────────────────────


def test_list_global(storage: Path) -> None:
    _write_manifest(
        storage / "global.json",
        ["@python", "skill:code-review", "agent:researcher"],
    )

    result = CliRunner().invoke(list_cmd, ["-g"])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "Global (global.json):" in out
    assert "@python" in out
    assert "skill:code-review" in out
    assert "agent:researcher" in out
    # With -g only the Global section is shown; no Project header
    assert "Project" not in out


# ── list --available ──────────────────────────────────────────────────────


def test_list_available_domains(storage: Path) -> None:
    catalog = storage / "catalog"
    (catalog / "python").mkdir()
    (catalog / "go").mkdir()

    result = CliRunner().invoke(list_cmd, ["--available"])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "Available in catalog:" in out
    assert "Domains:" in out
    assert "@python" in out
    assert "@go" in out


def test_list_available_standalone(storage: Path) -> None:
    catalog = storage / "catalog"
    (catalog / "skills" / "code-review").mkdir(parents=True)
    (catalog / "skills" / "code-review" / "SKILL.md").write_text("# cr\n")
    (catalog / "skills" / "git-workflow").mkdir(parents=True)
    (catalog / "skills" / "git-workflow" / "SKILL.md").write_text("# gw\n")
    (catalog / "agents").mkdir(parents=True)
    (catalog / "agents" / "researcher.md").write_text("# r\n")
    (catalog / "agents" / "reviewer.md").write_text("# rev\n")
    (catalog / "rules").mkdir(parents=True)
    (catalog / "rules" / "security.md").write_text("# sec\n")

    result = CliRunner().invoke(list_cmd, ["--available"])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "skill:code-review" in out
    assert "skill:git-workflow" in out
    assert "agent:researcher" in out
    assert "agent:reviewer" in out
    assert "rule:security" in out


def test_list_available_skips_example(storage: Path) -> None:
    catalog = storage / "catalog"
    (catalog / "python").mkdir()
    (catalog / "_example").mkdir()
    # Reserved subdirs must not be listed as domains either.
    (catalog / "skills").mkdir()
    (catalog / "agents").mkdir()
    (catalog / "rules").mkdir()

    result = CliRunner().invoke(list_cmd, ["--available"])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "@python" in out
    assert "@_example" not in out
    # The reserved subdirs should not appear as domain entries.
    assert "@skills" not in out
    assert "@agents" not in out
    assert "@rules" not in out

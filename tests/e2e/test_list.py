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
    (storage_dir / "stacks").mkdir()
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
    assert "Packages (ai-dotfiles.json):" in out
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


def test_list_project_empty(storage: Path, project: Path) -> None:
    _write_manifest(project / "ai-dotfiles.json", [])

    result = CliRunner().invoke(list_cmd, [])

    assert result.exit_code == 0, result.output
    assert "No packages installed." in result.output


def test_list_project_missing_manifest(storage: Path, project: Path) -> None:
    result = CliRunner().invoke(list_cmd, [])

    assert result.exit_code != 0
    # ui.error writes to stderr; CliRunner captures both in .output by default.
    assert "ai-dotfiles.json not found" in result.output


# ── list -g ───────────────────────────────────────────────────────────────


def test_list_global(storage: Path) -> None:
    _write_manifest(
        storage / "global.json",
        ["@python", "skill:code-review", "agent:researcher"],
    )

    result = CliRunner().invoke(list_cmd, ["-g"])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "Packages (global.json):" in out
    assert "@python" in out
    assert "skill:code-review" in out
    assert "agent:researcher" in out


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


def test_list_available_stacks(storage: Path) -> None:
    stacks = storage / "stacks"
    (stacks / "backend.conf").write_text("@python\n")
    (stacks / "frontend.conf").write_text("@typescript\n")
    # Non-.conf files are ignored.
    (stacks / "README.md").write_text("# stacks\n")

    result = CliRunner().invoke(list_cmd, ["--available"])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "Stacks:" in out
    assert "backend" in out
    assert "frontend" in out
    # README should not appear as a stack entry.
    lines = [line.strip() for line in out.splitlines()]
    assert "README" not in lines


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

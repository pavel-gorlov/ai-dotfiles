"""Integration tests for .gitignore auto-management in add/remove/install."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.add import add
from ai_dotfiles.commands.install import install
from ai_dotfiles.commands.remove import remove
from ai_dotfiles.core.gitignore import MANAGED_END, MANAGED_START

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
    domain = cat / "testdomain"
    (domain / "skills" / "test-skill").mkdir(parents=True)
    (domain / "skills" / "test-skill" / "SKILL.md").write_text("x", encoding="utf-8")
    (domain / "agents").mkdir()
    (domain / "agents" / "test-agent.md").write_text("x", encoding="utf-8")

    # Second domain for multi-add tests.
    second = cat / "seconddomain"
    (second / "skills" / "second-skill").mkdir(parents=True)
    (second / "skills" / "second-skill" / "SKILL.md").write_text("x", encoding="utf-8")
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


def _read_gitignore(project: Path) -> str:
    path = project / ".gitignore"
    return path.read_text(encoding="utf-8") if path.exists() else ""


# ── add ─────────────────────────────────────────────────────────────────────


def test_add_creates_managed_block_with_linked_paths(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    result = runner.invoke(add, ["@testdomain"])
    assert result.exit_code == 0, result.output

    text = _read_gitignore(project)
    assert MANAGED_START in text
    assert MANAGED_END in text
    assert "/.claude/skills/test-skill" in text
    assert "/.claude/agents/test-agent.md" in text


def test_add_preserves_user_authored_lines_above_and_below(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    (project / ".gitignore").write_text("node_modules/\n*.log\n", encoding="utf-8")
    runner.invoke(add, ["@testdomain"])

    text = _read_gitignore(project)
    assert "node_modules/" in text
    assert "*.log" in text
    assert MANAGED_START in text
    assert "/.claude/skills/test-skill" in text


def test_add_is_idempotent_second_run_does_not_change_file(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    runner.invoke(add, ["@testdomain"])
    first = (project / ".gitignore").read_bytes()

    # Second add is a no-op on the manifest but still runs sync_gitignore.
    runner.invoke(add, ["@testdomain"])
    second = (project / ".gitignore").read_bytes()
    assert first == second


def test_add_skips_when_no_git_and_no_gitignore(
    runner: CliRunner, catalog: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Project-without-git fixture: has ai-dotfiles.json but no .git and
    # no .gitignore — sync must be a silent no-op.
    proj = tmp_path / "no-git-proj"
    proj.mkdir()
    (proj / "ai-dotfiles.json").write_text(
        json.dumps({"packages": []}) + "\n", encoding="utf-8"
    )
    monkeypatch.chdir(proj)

    result = runner.invoke(add, ["@testdomain"])
    assert result.exit_code == 0, result.output
    assert not (proj / ".gitignore").exists()


def test_add_manages_gitignore_when_file_present_without_git(
    runner: CliRunner,
    catalog: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proj = tmp_path / "no-git-but-ignore"
    proj.mkdir()
    (proj / "ai-dotfiles.json").write_text(
        json.dumps({"packages": []}) + "\n", encoding="utf-8"
    )
    (proj / ".gitignore").write_text("tmp/\n", encoding="utf-8")
    monkeypatch.chdir(proj)

    result = runner.invoke(add, ["@testdomain"])
    assert result.exit_code == 0, result.output

    text = (proj / ".gitignore").read_text(encoding="utf-8")
    assert "tmp/" in text
    assert "/.claude/skills/test-skill" in text


def test_add_does_not_duplicate_paths_already_in_user_lines(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    (project / ".gitignore").write_text(
        "/.claude/skills/test-skill\n", encoding="utf-8"
    )
    runner.invoke(add, ["@testdomain"])

    text = _read_gitignore(project)
    # Count the literal path — must appear exactly once (in the user line,
    # not in the managed block).
    assert text.count("/.claude/skills/test-skill") == 1


# ── remove ──────────────────────────────────────────────────────────────────


def test_remove_shrinks_block_to_remaining_symlinks(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    runner.invoke(add, ["@testdomain", "@seconddomain"])
    runner.invoke(remove, ["@testdomain"])

    text = _read_gitignore(project)
    assert "/.claude/skills/test-skill" not in text
    assert "/.claude/skills/second-skill" in text


def test_remove_deletes_block_markers_when_no_symlinks_left(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    runner.invoke(add, ["@testdomain"])
    runner.invoke(remove, ["@testdomain"])

    text = _read_gitignore(project)
    assert MANAGED_START not in text
    assert MANAGED_END not in text


def test_remove_leaves_user_authored_lines_intact(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    (project / ".gitignore").write_text("node_modules/\n*.log\n", encoding="utf-8")
    runner.invoke(add, ["@testdomain"])
    runner.invoke(remove, ["@testdomain"])

    text = _read_gitignore(project)
    assert "node_modules/" in text
    assert "*.log" in text


# ── install ────────────────────────────────────────────────────────────────


def test_install_regenerates_block_from_current_symlinks(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    runner.invoke(add, ["@testdomain"])

    # Manually blow away the managed block — simulate a stale .gitignore.
    (project / ".gitignore").write_text("node_modules/\n", encoding="utf-8")

    result = runner.invoke(install, [])
    assert result.exit_code == 0, result.output

    text = _read_gitignore(project)
    assert "/.claude/skills/test-skill" in text
    assert MANAGED_START in text
    assert "node_modules/" in text


# ── opt-out ─────────────────────────────────────────────────────────────────


def test_no_gitignore_flag_on_add_skips_sync(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    result = runner.invoke(add, ["@testdomain", "--no-gitignore"])
    assert result.exit_code == 0, result.output
    assert not (project / ".gitignore").exists()


def test_no_gitignore_flag_on_remove_skips_sync(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    runner.invoke(add, ["@testdomain"])
    before = _read_gitignore(project)
    assert MANAGED_START in before

    result = runner.invoke(remove, ["@testdomain", "--no-gitignore"])
    assert result.exit_code == 0, result.output

    # Block left untouched because sync was skipped.
    assert _read_gitignore(project) == before


def test_no_gitignore_flag_on_install_skips_sync(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    (project / "ai-dotfiles.json").write_text(
        json.dumps({"packages": []}) + "\n", encoding="utf-8"
    )
    result = runner.invoke(install, ["--no-gitignore"])
    assert result.exit_code == 0, result.output
    assert not (project / ".gitignore").exists()


def test_project_manage_gitignore_false_disables_sync(
    runner: CliRunner, catalog: Path, project: Path
) -> None:
    (project / "ai-dotfiles.json").write_text(
        json.dumps({"packages": [], "manage_gitignore": False}) + "\n",
        encoding="utf-8",
    )
    result = runner.invoke(add, ["@testdomain"])
    assert result.exit_code == 0, result.output
    assert not (project / ".gitignore").exists()


def test_global_manage_gitignore_false_disables_sync(
    runner: CliRunner, catalog: Path, project: Path, storage: Path
) -> None:
    (storage / "global.json").write_text(
        json.dumps({"packages": [], "manage_gitignore": False}) + "\n",
        encoding="utf-8",
    )
    result = runner.invoke(add, ["@testdomain"])
    assert result.exit_code == 0, result.output
    assert not (project / ".gitignore").exists()


def test_global_false_blocks_even_when_project_true(
    runner: CliRunner, catalog: Path, project: Path, storage: Path
) -> None:
    # Project flag True (default) + global False -> global blocks (both
    # must be True for us to manage).
    (project / "ai-dotfiles.json").write_text(
        json.dumps({"packages": [], "manage_gitignore": True}) + "\n",
        encoding="utf-8",
    )
    (storage / "global.json").write_text(
        json.dumps({"packages": [], "manage_gitignore": False}) + "\n",
        encoding="utf-8",
    )
    runner.invoke(add, ["@testdomain"])
    # Global says false -> no gitignore written.
    assert not (project / ".gitignore").exists()


def test_project_false_is_authoritative_even_when_global_true(
    runner: CliRunner, catalog: Path, project: Path, storage: Path
) -> None:
    (project / "ai-dotfiles.json").write_text(
        json.dumps({"packages": [], "manage_gitignore": False}) + "\n",
        encoding="utf-8",
    )
    (storage / "global.json").write_text(
        json.dumps({"packages": [], "manage_gitignore": True}) + "\n",
        encoding="utf-8",
    )
    runner.invoke(add, ["@testdomain"])
    assert not (project / ".gitignore").exists()


# ── global scope ────────────────────────────────────────────────────────────


def test_global_install_never_touches_home_gitignore(
    runner: CliRunner, catalog: Path, storage: Path, home: Path
) -> None:
    # Seed global manifest empty so install -g does nothing problematic.
    (storage / "global.json").write_text(
        json.dumps({"packages": []}) + "\n", encoding="utf-8"
    )
    (storage / "global").mkdir()

    result = runner.invoke(install, ["-g"])
    assert result.exit_code == 0, result.output
    assert not (home / ".gitignore").exists()
    assert not (home / ".claude" / ".gitignore").exists()

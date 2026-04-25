"""E2E tests for ``ai-dotfiles stack`` subcommand group."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.stack import (
    _read_stack,
    _stack_path,
    _write_stack,
    stack,
)
from ai_dotfiles.core import manifest

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
    (storage_dir / "stacks").mkdir()
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage_dir))
    return storage_dir


@pytest.fixture
def catalog(storage: Path) -> Path:
    """Populate catalog with a domain, standalone skill, agent, rule."""
    cat = storage / "catalog"

    # Domain `python` with a skill, agent, and settings fragment.
    domain = cat / "python"
    (domain / "skills" / "py-skill").mkdir(parents=True)
    (domain / "skills" / "py-skill" / "SKILL.md").write_text("py skill\n")
    (domain / "agents").mkdir()
    (domain / "agents" / "py-agent.md").write_text("# py agent\n")
    (domain / "domain.json").write_text(json.dumps({"name": "python"}))
    (domain / "settings.fragment.json").write_text(
        json.dumps({"permissions": {"allow": ["Read"]}})
    )

    # Standalone skill / agent / rule.
    (cat / "skills" / "code-review").mkdir(parents=True)
    (cat / "skills" / "code-review" / "SKILL.md").write_text("review\n")

    (cat / "agents").mkdir(exist_ok=True)
    (cat / "agents" / "researcher.md").write_text("# researcher\n")

    (cat / "rules").mkdir()
    (cat / "rules" / "security.md").write_text("# security\n")

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


# ── Helper tests ──────────────────────────────────────────────────────────


def test_read_stack_skips_comments(storage: Path) -> None:
    path = storage / "stacks" / "mix.conf"
    path.write_text("# header\n@python\n# comment\nskill:code-review\n")
    assert _read_stack(path) == ["@python", "skill:code-review"]


def test_read_stack_skips_blank_lines(storage: Path) -> None:
    path = storage / "stacks" / "blanks.conf"
    path.write_text("\n@python\n\n\nskill:code-review\n\n")
    assert _read_stack(path) == ["@python", "skill:code-review"]


# ── create ────────────────────────────────────────────────────────────────


def test_stack_create(runner: CliRunner, storage: Path) -> None:
    result = runner.invoke(stack, ["create", "backend"])
    assert result.exit_code == 0, result.output
    path = _stack_path("backend")
    assert path.exists()
    content = path.read_text()
    assert "# Stack: backend" in content
    assert "ai-dotfiles stack apply backend" in content
    assert "backend" in result.output


def test_stack_create_already_exists(runner: CliRunner, storage: Path) -> None:
    _write_stack(_stack_path("dup"), [], "dup")
    result = runner.invoke(stack, ["create", "dup"])
    assert result.exit_code != 0
    assert "already exists" in result.output


# ── delete ────────────────────────────────────────────────────────────────


def test_stack_delete(runner: CliRunner, storage: Path) -> None:
    _write_stack(_stack_path("tmp"), [], "tmp")
    result = runner.invoke(stack, ["delete", "tmp"])
    assert result.exit_code == 0, result.output
    assert not _stack_path("tmp").exists()


def test_stack_delete_not_found(runner: CliRunner, storage: Path) -> None:
    result = runner.invoke(stack, ["delete", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output


# ── list ──────────────────────────────────────────────────────────────────


def test_stack_list_populated(runner: CliRunner, storage: Path) -> None:
    _write_stack(_stack_path("s"), ["@python", "skill:code-review"], "s")
    result = runner.invoke(stack, ["list", "s"])
    assert result.exit_code == 0, result.output
    assert "@python" in result.output
    assert "skill:code-review" in result.output


def test_stack_list_empty(runner: CliRunner, storage: Path) -> None:
    _write_stack(_stack_path("empty"), [], "empty")
    result = runner.invoke(stack, ["list", "empty"])
    assert result.exit_code == 0, result.output
    assert "empty" in result.output


# ── add ───────────────────────────────────────────────────────────────────


def test_stack_add_items(runner: CliRunner, storage: Path) -> None:
    _write_stack(_stack_path("s"), ["@python"], "s")
    result = runner.invoke(stack, ["add", "s", "skill:code-review", "rule:security"])
    assert result.exit_code == 0, result.output
    items = _read_stack(_stack_path("s"))
    assert items == ["@python", "skill:code-review", "rule:security"]


def test_stack_add_duplicate(runner: CliRunner, storage: Path) -> None:
    _write_stack(_stack_path("s"), ["@python"], "s")
    result = runner.invoke(stack, ["add", "s", "@python"])
    assert result.exit_code == 0, result.output
    items = _read_stack(_stack_path("s"))
    assert items == ["@python"]
    assert "already in stack" in result.output


def test_stack_add_invalid_format(runner: CliRunner, storage: Path) -> None:
    _write_stack(_stack_path("s"), [], "s")
    result = runner.invoke(stack, ["add", "s", "not-a-spec"])
    assert result.exit_code != 0
    # Stack file should not have been modified.
    assert _read_stack(_stack_path("s")) == []


# ── remove ────────────────────────────────────────────────────────────────


def test_stack_remove_items(runner: CliRunner, storage: Path) -> None:
    _write_stack(_stack_path("s"), ["@python", "skill:code-review"], "s")
    result = runner.invoke(stack, ["remove", "s", "@python"])
    assert result.exit_code == 0, result.output
    items = _read_stack(_stack_path("s"))
    assert items == ["skill:code-review"]


def test_stack_remove_not_present(runner: CliRunner, storage: Path) -> None:
    _write_stack(_stack_path("s"), ["@python"], "s")
    result = runner.invoke(stack, ["remove", "s", "skill:ghost"])
    # Warning, not error.
    assert result.exit_code == 0, result.output
    assert "not in stack" in result.output
    assert _read_stack(_stack_path("s")) == ["@python"]


# ── apply ─────────────────────────────────────────────────────────────────


def test_stack_apply(
    runner: CliRunner, catalog: Path, storage: Path, project: Path
) -> None:
    _write_stack(
        _stack_path("full"),
        ["@python", "skill:code-review", "agent:researcher", "rule:security"],
        "full",
    )
    result = runner.invoke(stack, ["apply", "full"])
    assert result.exit_code == 0, result.output

    # Manifest has the packages.
    pkgs = manifest.get_packages(project / "ai-dotfiles.json")
    assert pkgs == [
        "@python",
        "skill:code-review",
        "agent:researcher",
        "rule:security",
    ]

    # Symlinks created.
    claude = project / ".claude"
    assert (claude / "skills" / "py-skill").is_symlink()
    assert (claude / "agents" / "py-agent.md").is_symlink()
    assert (claude / "skills" / "code-review").is_symlink()
    assert (claude / "agents" / "researcher.md").is_symlink()
    assert (claude / "rules" / "security.md").is_symlink()


def test_stack_apply_sets_stack_key(
    runner: CliRunner, catalog: Path, storage: Path, project: Path
) -> None:
    _write_stack(_stack_path("marker"), ["skill:code-review"], "marker")
    result = runner.invoke(stack, ["apply", "marker"])
    assert result.exit_code == 0, result.output

    data = json.loads((project / "ai-dotfiles.json").read_text())
    assert data.get("stack") == "marker"

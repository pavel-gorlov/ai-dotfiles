"""End-to-end tests for ``ai-dotfiles domain``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.domain import domain


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
    (storage_dir / "catalog").mkdir()
    (storage_dir / "stacks").mkdir()
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage_dir))
    return storage_dir


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _catalog(storage: Path) -> Path:
    return storage / "catalog"


# ── create ───────────────────────────────────────────────────────────────


def test_domain_create(runner: CliRunner, storage: Path) -> None:
    result = runner.invoke(domain, ["create", "python"])
    assert result.exit_code == 0, result.output

    domain_dir = _catalog(storage) / "python"
    assert domain_dir.is_dir()
    for sub in ("skills", "agents", "rules", "hooks"):
        assert (domain_dir / sub).is_dir()
    assert (domain_dir / "domain.json").is_file()
    assert "Created domain @python" in result.output


def test_domain_create_already_exists(runner: CliRunner, storage: Path) -> None:
    (_catalog(storage) / "python").mkdir()
    result = runner.invoke(domain, ["create", "python"])
    assert result.exit_code != 0
    assert "already exists" in result.output


def test_domain_create_writes_domain_json(runner: CliRunner, storage: Path) -> None:
    result = runner.invoke(domain, ["create", "rust"])
    assert result.exit_code == 0, result.output

    meta_path = _catalog(storage) / "rust" / "domain.json"
    data = json.loads(meta_path.read_text())
    assert data["name"] == "rust"
    assert "description" in data


# ── delete ───────────────────────────────────────────────────────────────


def test_domain_delete(runner: CliRunner, storage: Path) -> None:
    path = _catalog(storage) / "python"
    path.mkdir()
    result = runner.invoke(domain, ["delete", "python", "-y"])
    assert result.exit_code == 0, result.output
    assert not path.exists()
    assert "Deleted domain @python" in result.output


def test_domain_delete_example_blocked(runner: CliRunner, storage: Path) -> None:
    (_catalog(storage) / "_example").mkdir()
    result = runner.invoke(domain, ["delete", "_example", "-y"])
    assert result.exit_code != 0
    assert "Cannot delete" in result.output
    assert (_catalog(storage) / "_example").is_dir()


def test_domain_delete_warns_usage(runner: CliRunner, storage: Path) -> None:
    (_catalog(storage) / "python").mkdir()
    # Reference the domain from global.json.
    (storage / "global.json").write_text(
        json.dumps({"packages": ["@python"]}), encoding="utf-8"
    )
    result = runner.invoke(domain, ["delete", "python", "-y"])
    assert result.exit_code == 0, result.output
    assert "referenced in" in result.output
    assert "global.json" in result.output


def test_domain_delete_not_found(runner: CliRunner, storage: Path) -> None:
    result = runner.invoke(domain, ["delete", "missing", "-y"])
    assert result.exit_code != 0
    assert "not found" in result.output


# ── list ─────────────────────────────────────────────────────────────────


def test_domain_list(runner: CliRunner, storage: Path) -> None:
    root = _catalog(storage) / "python"
    (root / "skills" / "py-lint").mkdir(parents=True)
    (root / "skills" / "py-lint" / "SKILL.md").write_text("x")
    (root / "agents").mkdir()
    (root / "agents" / "py-debug.md").write_text("x")
    (root / "rules").mkdir()
    (root / "hooks").mkdir()
    (root / "hooks" / "ruff-on-save.sh").write_text("#!/bin/sh\n")
    (root / "settings.fragment.json").write_text("{}")

    result = runner.invoke(domain, ["list", "python"])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "Domain @python" in out
    assert "py-lint" in out
    assert "py-debug" in out
    assert "ruff-on-save.sh" in out
    assert "rules:" in out
    assert "(empty)" in out  # for rules
    assert "settings.fragment.json: yes" in out


def test_domain_list_empty(runner: CliRunner, storage: Path) -> None:
    root = _catalog(storage) / "empty"
    for sub in ("skills", "agents", "rules", "hooks"):
        (root / sub).mkdir(parents=True)

    result = runner.invoke(domain, ["list", "empty"])
    assert result.exit_code == 0, result.output
    out = result.output
    # Each of the four categories should render as (empty).
    assert out.count("(empty)") == 4
    assert "settings.fragment.json: no" in out


def test_domain_list_not_found(runner: CliRunner, storage: Path) -> None:
    result = runner.invoke(domain, ["list", "ghost"])
    assert result.exit_code != 0
    assert "not found" in result.output


# ── add ──────────────────────────────────────────────────────────────────


def test_domain_add_skill(runner: CliRunner, storage: Path) -> None:
    (_catalog(storage) / "python").mkdir()
    result = runner.invoke(domain, ["add", "python", "skill", "py-lint"])
    assert result.exit_code == 0, result.output

    skill_md = _catalog(storage) / "python" / "skills" / "py-lint" / "SKILL.md"
    assert skill_md.is_file()
    assert "py-lint" in skill_md.read_text()
    assert "Created skill py-lint in domain @python" in result.output


def test_domain_add_agent(runner: CliRunner, storage: Path) -> None:
    (_catalog(storage) / "python").mkdir()
    result = runner.invoke(domain, ["add", "python", "agent", "py-debug"])
    assert result.exit_code == 0, result.output

    agent_md = _catalog(storage) / "python" / "agents" / "py-debug.md"
    assert agent_md.is_file()
    assert "py-debug" in agent_md.read_text()


def test_domain_add_rule(runner: CliRunner, storage: Path) -> None:
    (_catalog(storage) / "python").mkdir()
    result = runner.invoke(domain, ["add", "python", "rule", "py-style"])
    assert result.exit_code == 0, result.output

    rule_md = _catalog(storage) / "python" / "rules" / "py-style.md"
    assert rule_md.is_file()
    assert "py-style" in rule_md.read_text()


def test_domain_add_already_exists(runner: CliRunner, storage: Path) -> None:
    root = _catalog(storage) / "python"
    (root / "skills" / "py-lint").mkdir(parents=True)
    (root / "skills" / "py-lint" / "SKILL.md").write_text("existing")

    result = runner.invoke(domain, ["add", "python", "skill", "py-lint"])
    assert result.exit_code != 0
    assert "already exists" in result.output


def test_domain_add_domain_missing(runner: CliRunner, storage: Path) -> None:
    result = runner.invoke(domain, ["add", "ghost", "skill", "x"])
    assert result.exit_code != 0
    assert "not found" in result.output


# ── remove ───────────────────────────────────────────────────────────────


def test_domain_remove_skill(runner: CliRunner, storage: Path) -> None:
    root = _catalog(storage) / "python"
    skill_dir = root / "skills" / "py-lint"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("x")

    result = runner.invoke(domain, ["remove", "python", "skill", "py-lint"])
    assert result.exit_code == 0, result.output
    assert not skill_dir.exists()
    assert "Removed skill py-lint from domain @python" in result.output


def test_domain_remove_agent(runner: CliRunner, storage: Path) -> None:
    root = _catalog(storage) / "python"
    (root / "agents").mkdir(parents=True)
    agent = root / "agents" / "py-debug.md"
    agent.write_text("x")

    result = runner.invoke(domain, ["remove", "python", "agent", "py-debug"])
    assert result.exit_code == 0, result.output
    assert not agent.exists()


def test_domain_remove_not_found(runner: CliRunner, storage: Path) -> None:
    (_catalog(storage) / "python").mkdir()
    result = runner.invoke(domain, ["remove", "python", "skill", "ghost"])
    assert result.exit_code != 0
    assert "not found" in result.output

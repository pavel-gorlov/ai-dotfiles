"""E2E test for ``ai-dotfiles migrate`` via the full CLI (CliRunner)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.cli import cli


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    storage = home / ".ai-dotfiles"
    (storage / "catalog").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage))

    proj = home / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / "ai-dotfiles.json").write_text(
        json.dumps({"packages": []}), encoding="utf-8"
    )
    _write(
        proj / ".claude" / "skills" / "myskill" / "SKILL.md",
        "---\nname: myskill\ndescription: A local skill.\n---\nBody.\n",
    )
    _write(proj / "CLAUDE.md", "# Project\n")
    monkeypatch.chdir(proj)
    return proj


def test_migrate_dry_run_then_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = _project(tmp_path, monkeypatch)
    runner = CliRunner()

    dry = runner.invoke(cli, ["migrate", "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "Dry run" in dry.output
    assert not (proj / ".agents").exists()

    applied = runner.invoke(cli, ["migrate"])
    assert applied.exit_code == 0, applied.output
    assert (proj / ".agents" / "skills" / "myskill").is_symlink()

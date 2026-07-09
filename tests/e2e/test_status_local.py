"""E2E: ``ai-dotfiles status`` surfaces LOCAL elements and Claude-only surfaces."""

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
        proj / ".claude" / "skills" / "local-skill" / "SKILL.md",
        "---\nname: local-skill\ndescription: A local skill.\n---\nBody.\n",
    )
    _write(proj / ".claude" / "workflows" / "recipe.js", "// bespoke\n")
    _write(proj / "CLAUDE.md", "# Project\n")
    monkeypatch.chdir(proj)
    return proj


def test_status_lists_local_and_claude_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project(tmp_path, monkeypatch)
    runner = CliRunner()

    before = runner.invoke(cli, ["status"])
    assert before.exit_code == 0, before.output
    assert "Local (non-catalog) elements" in before.output
    assert "skill:local-skill" in before.output
    assert "not migrated" in before.output
    assert "Claude-only (no Codex target)" in before.output
    assert "workflows/recipe.js" in before.output

    assert runner.invoke(cli, ["migrate"]).exit_code == 0

    after = runner.invoke(cli, ["status"])
    assert after.exit_code == 0, after.output
    assert "skill:local-skill" in after.output
    assert "migrated to Codex" in after.output

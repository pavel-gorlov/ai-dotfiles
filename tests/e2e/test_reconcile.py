"""E2E test for ``ai-dotfiles reconcile`` via the full CLI (CliRunner)."""

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
    # A rendered local skill (description over the 1024 cap) so edits drift.
    _write(
        proj / ".claude" / "skills" / "big" / "SKILL.md",
        f"---\nname: big\ndescription: {'x' * 1100}\n---\nBody.\n",
    )
    _write(proj / "CLAUDE.md", "# Project\n")
    monkeypatch.chdir(proj)
    return proj


def test_reconcile_check_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = _project(tmp_path, monkeypatch)
    runner = CliRunner()

    assert runner.invoke(cli, ["migrate"]).exit_code == 0

    # Fresh -> check passes.
    assert runner.invoke(cli, ["reconcile", "--check"]).exit_code == 0

    # Edit the source -> the rendered artefact is stale -> check fails.
    _write(
        proj / ".claude" / "skills" / "big" / "SKILL.md",
        f"---\nname: big\ndescription: {'y' * 1100}\n---\nChanged.\n",
    )
    drifted = runner.invoke(cli, ["reconcile", "--check"])
    assert drifted.exit_code == 1
    assert "big" in drifted.output

    # Repair, then check passes again.
    assert runner.invoke(cli, ["reconcile"]).exit_code == 0
    assert runner.invoke(cli, ["reconcile", "--check"]).exit_code == 0

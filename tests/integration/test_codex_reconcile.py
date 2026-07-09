"""Reconcile stale/missing Codex artefacts (``ai-dotfiles reconcile``)."""

from pathlib import Path

import pytest

from ai_dotfiles.core import codex_migrate, codex_reconcile, paths

pytestmark = pytest.mark.integration


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build(root: Path) -> None:
    claude = root / ".claude"
    # rendered skill (description over Codex's 1024 cap) + symlinked skill
    _write(
        claude / "skills" / "big-skill" / "SKILL.md",
        f"---\nname: big-skill\ndescription: {'x' * 1100}\n---\nBody.\n",
    )
    _write(
        claude / "skills" / "lil-skill" / "SKILL.md",
        "---\nname: lil-skill\ndescription: Short.\n---\nBody.\n",
    )
    _write(
        claude / "agents" / "ag.md",
        "---\nname: ag\ndescription: An agent.\n---\nInstructions.\n",
    )
    _write(root / "CLAUDE.md", "# Project\n")


def _reconcile(root: Path, *, check: bool) -> codex_reconcile.ReconcileReport:
    return codex_reconcile.reconcile_codex(
        root, [], paths.catalog_dir(), check_only=check, include_catalog=False
    )


def test_reconcile_clean_after_migrate(tmp_path: Path, tmp_storage: Path) -> None:
    root = tmp_path / "proj"
    _build(root)
    codex_migrate.migrate_to_codex(root, manifest_packages=[])

    assert _reconcile(root, check=True).drift == []


def test_reconcile_detects_and_fixes_rendered_drift(
    tmp_path: Path, tmp_storage: Path
) -> None:
    root = tmp_path / "proj"
    _build(root)
    codex_migrate.migrate_to_codex(root, manifest_packages=[])

    # Edit the rendered skill's source -> its generated SKILL.md is now stale.
    _write(
        root / ".claude" / "skills" / "big-skill" / "SKILL.md",
        f"---\nname: big-skill\ndescription: {'y' * 1100}\n---\nChanged body.\n",
    )

    assert "local skills/big-skill" in _reconcile(root, check=True).drift

    fixed = _reconcile(root, check=False)
    assert "local skills/big-skill" in fixed.drift  # was repaired
    assert _reconcile(root, check=True).drift == []  # clean again


def test_reconcile_ignores_symlinked_skill_source_edits(
    tmp_path: Path, tmp_storage: Path
) -> None:
    root = tmp_path / "proj"
    _build(root)
    codex_migrate.migrate_to_codex(root, manifest_packages=[])

    # Editing a symlinked skill's source never drifts — the link is auto-fresh.
    _write(
        root / ".claude" / "skills" / "lil-skill" / "SKILL.md",
        "---\nname: lil-skill\ndescription: Short, edited.\n---\nNew body.\n",
    )

    assert not any("lil-skill" in label for label in _reconcile(root, check=True).drift)


def test_reconcile_regenerates_missing_agent(tmp_path: Path, tmp_storage: Path) -> None:
    root = tmp_path / "proj"
    _build(root)
    codex_migrate.migrate_to_codex(root, manifest_packages=[])

    (paths.project_codex_agents_dir(root) / "ag.toml").unlink()

    assert "local agents/ag" in _reconcile(root, check=True).drift
    _reconcile(root, check=False)
    assert (paths.project_codex_agents_dir(root) / "ag.toml").is_file()
    assert _reconcile(root, check=True).drift == []

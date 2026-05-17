"""Integration tests for ai_dotfiles.core.claude_copy.

These exercise the copy-mode primitives directly (without the CLI) so a
regression in copy / remove / prune is caught close to the source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_dotfiles.core.claude_copy import (
    copy_element,
    prune_copies,
    remove_copied_element,
)
from ai_dotfiles.core.copy_ownership import load_copy_ownership
from ai_dotfiles.core.elements import parse_element

pytestmark = pytest.mark.integration


def _make_skill(catalog: Path, name: str, body: str = "") -> None:
    sdir = catalog / "skills" / name
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "SKILL.md").write_text(body or f"# {name}\n", encoding="utf-8")


def test_copy_element_writes_files_and_records_ownership(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    claude = tmp_path / ".claude"
    _make_skill(catalog, "code-review")

    labels = copy_element(parse_element("skill:code-review"), claude, catalog)

    assert labels == ["skills/code-review"]
    target = claude / "skills" / "code-review"
    assert target.is_dir() and not target.is_symlink()
    assert load_copy_ownership(claude) == {"skills/code-review"}


def test_copy_element_executable_bit_preserved(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    claude = tmp_path / ".claude"
    sdir = catalog / "skills" / "tool"
    (sdir / "scripts").mkdir(parents=True)
    (sdir / "SKILL.md").write_text("# tool\n")
    script = sdir / "scripts" / "run.sh"
    script.write_text("#!/bin/sh\necho hi\n")
    script.chmod(0o755)

    copy_element(parse_element("skill:tool"), claude, catalog)

    copied = claude / "skills" / "tool" / "scripts" / "run.sh"
    assert copied.stat().st_mode & 0o111  # some execute bit set


def test_remove_copied_element_deletes_and_updates_sidecar(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    claude = tmp_path / ".claude"
    _make_skill(catalog, "a")
    _make_skill(catalog, "b")
    copy_element(parse_element("skill:a"), claude, catalog)
    copy_element(parse_element("skill:b"), claude, catalog)

    removed = remove_copied_element(parse_element("skill:a"), claude, catalog)

    assert removed == ["skills/a"]
    assert not (claude / "skills" / "a").exists()
    assert (claude / "skills" / "b").is_dir()
    assert load_copy_ownership(claude) == {"skills/b"}


def test_remove_copied_element_skips_unowned_path(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    claude = tmp_path / ".claude"
    _make_skill(catalog, "ghost")
    # A real directory at the target that ai-dotfiles never recorded.
    user = claude / "skills" / "ghost"
    user.mkdir(parents=True)
    (user / "SKILL.md").write_text("# user\n")

    removed = remove_copied_element(parse_element("skill:ghost"), claude, catalog)

    assert removed == []
    assert (user / "SKILL.md").read_text() == "# user\n"


def test_prune_copies_removes_stale_only(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    claude = tmp_path / ".claude"
    _make_skill(catalog, "keep")
    _make_skill(catalog, "stale")
    copy_element(parse_element("skill:keep"), claude, catalog)
    copy_element(parse_element("skill:stale"), claude, catalog)

    # Manifest now only wants `keep`.
    pruned = prune_copies([parse_element("skill:keep")], claude, catalog)

    assert pruned == ["skills/stale"]
    assert (claude / "skills" / "keep").is_dir()
    assert not (claude / "skills" / "stale").exists()
    assert load_copy_ownership(claude) == {"skills/keep"}


def test_prune_copies_noop_when_nothing_owned(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    claude = tmp_path / ".claude"
    claude.mkdir()
    assert prune_copies([], claude, catalog) == []

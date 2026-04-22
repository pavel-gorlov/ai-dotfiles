"""Integration tests for ``ai-dotfiles install --prune``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.commands.install import install
from ai_dotfiles.core import symlinks

pytestmark = pytest.mark.integration


def _seed_catalog(catalog: Path) -> None:
    """Build a minimal catalog with one domain + one skill inside it."""
    skill = catalog / "gitflow" / "skills" / "commit"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: commit\n---\n# commit\n")


def test_prune_dangling_removes_broken_symlinks_into_storage(
    tmp_storage: Path, tmp_path: Path
) -> None:
    """Direct prune_dangling: only catalog-pointing broken symlinks get removed."""
    claude = tmp_path / ".claude"
    (claude / "skills").mkdir(parents=True)

    # 1. Valid symlink into catalog
    valid_src = tmp_storage / "catalog" / "keep"
    valid_src.mkdir(parents=True)
    valid = claude / "skills" / "keep"
    valid.symlink_to(valid_src)

    # 2. Dangling symlink into catalog (should be removed)
    dangling = claude / "skills" / "vanished"
    dangling.symlink_to(tmp_storage / "catalog" / "vanished")

    # 3. User's own symlink to an external path (should be left alone)
    external = tmp_path / "external"
    external.mkdir()
    user_link = claude / "skills" / "user-own"
    user_link.symlink_to(external)

    # 4. Real file (not a symlink) — never touched
    real_file = claude / "CLAUDE.md"
    real_file.write_text("hi\n")

    removed = symlinks.prune_dangling(claude, tmp_storage)

    assert removed == ["skills/vanished"]
    assert valid.is_symlink()
    assert not dangling.exists() and not dangling.is_symlink()
    assert user_link.is_symlink()
    assert real_file.is_file()


def test_install_global_prune_cleans_after_rename(
    tmp_storage: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate a catalog rename: old symlink dangling, install --prune cleans it."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    catalog = tmp_storage / "catalog"
    _seed_catalog(catalog)

    # Global manifest references the new name
    (tmp_storage / "global.json").write_text(json.dumps({"packages": ["@gitflow"]}))

    # Pre-existing dangling symlink from a previous install of the "old" name
    claude = home / ".claude"
    (claude / "skills").mkdir(parents=True)
    old_link = claude / "skills" / "conventional-commit"
    old_link.symlink_to(catalog / "gitflow" / "skills" / "conventional-commit")
    assert old_link.is_symlink()
    assert not old_link.resolve().exists()  # confirms it's dangling

    runner = CliRunner()
    result = runner.invoke(install, ["-g", "--prune"])

    assert result.exit_code == 0, result.output

    # New link exists, old dangling link is gone
    assert (claude / "skills" / "commit").is_symlink()
    assert not old_link.exists() and not old_link.is_symlink()
    assert "Pruned 1 dangling symlink" in result.output
    assert "skills/conventional-commit" in result.output


def test_install_without_prune_keeps_dangling(
    tmp_storage: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default install (no --prune) must NOT remove dangling symlinks."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    catalog = tmp_storage / "catalog"
    _seed_catalog(catalog)
    (tmp_storage / "global.json").write_text(json.dumps({"packages": ["@gitflow"]}))

    claude = home / ".claude"
    (claude / "skills").mkdir(parents=True)
    old_link = claude / "skills" / "conventional-commit"
    old_link.symlink_to(catalog / "gitflow" / "skills" / "conventional-commit")

    result = CliRunner().invoke(install, ["-g"])

    assert result.exit_code == 0, result.output
    # New link exists but old dangling link also remains
    assert (claude / "skills" / "commit").is_symlink()
    assert old_link.is_symlink()
    assert "Pruned" not in result.output


def test_prune_skips_user_symlinks_outside_storage(
    tmp_storage: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Symlinks pointing outside ai-dotfiles storage must be left alone."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    catalog = tmp_storage / "catalog"
    _seed_catalog(catalog)
    (tmp_storage / "global.json").write_text(json.dumps({"packages": []}))

    claude = home / ".claude"
    (claude / "skills").mkdir(parents=True)

    # User's own symlink, pointing to a now-deleted path
    user_external = tmp_path / "user-stuff" / "my-skill"
    user_external.parent.mkdir()
    user_external.mkdir()
    user_link = claude / "skills" / "user-own"
    user_link.symlink_to(user_external)

    # Delete the user's own target to make it dangling — but since it's outside
    # storage, --prune must not touch it.
    import shutil

    shutil.rmtree(user_external.parent)

    result = CliRunner().invoke(install, ["-g", "--prune"])

    assert result.exit_code == 0, result.output
    assert user_link.is_symlink()  # untouched


def test_prune_empty_when_nothing_to_do(
    tmp_storage: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--prune with no dangling symlinks is silent about pruning."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    (tmp_storage / "catalog").mkdir()
    (tmp_storage / "global.json").write_text(json.dumps({"packages": []}))

    result = CliRunner().invoke(install, ["-g", "--prune"])

    assert result.exit_code == 0, result.output
    assert "Pruned" not in result.output

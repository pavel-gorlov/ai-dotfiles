"""Integration tests for ai_dotfiles.core.symlinks."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from ai_dotfiles.core.symlinks import (
    is_managed_symlink,
    link_domain,
    link_global_files,
    link_standalone,
    remove_symlink,
    safe_symlink,
    unlink_domain,
    unlink_standalone,
)

pytestmark = pytest.mark.integration


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated HOME for all tests in this module."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    return home_dir


@pytest.fixture
def storage(home: Path) -> Path:
    storage_dir = home / ".ai-dotfiles"
    storage_dir.mkdir()
    return storage_dir


@pytest.fixture
def backup(home: Path) -> Path:
    return home / ".dotfiles-backup"


@pytest.fixture
def claude_dir(home: Path) -> Path:
    claude = home / ".claude"
    claude.mkdir()
    return claude


def _make_file(path: Path, content: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


# ── safe_symlink ──────────────────────────────────────────────────────────


def test_safe_symlink_new(home: Path, backup: Path, storage: Path) -> None:
    source = _make_file(storage / "src.txt", "hi")
    target = home / ".claude" / "dst.txt"
    status = safe_symlink(source, target, backup)
    assert status == "linked"
    assert target.is_symlink()
    assert target.resolve() == source.resolve()


def test_safe_symlink_idempotent(home: Path, backup: Path, storage: Path) -> None:
    source = _make_file(storage / "src.txt")
    target = home / ".claude" / "dst.txt"
    assert safe_symlink(source, target, backup) == "linked"
    assert safe_symlink(source, target, backup) == "already-linked"


def test_safe_symlink_relink(home: Path, backup: Path, storage: Path) -> None:
    old = _make_file(storage / "old.txt", "old")
    new = _make_file(storage / "new.txt", "new")
    target = home / ".claude" / "dst.txt"
    safe_symlink(old, target, backup)
    status = safe_symlink(new, target, backup)
    assert status == "relinked"
    assert target.resolve() == new.resolve()


def test_safe_symlink_backup_file(
    home: Path, backup: Path, storage: Path, claude_dir: Path
) -> None:
    source = _make_file(storage / "src.txt", "linked")
    target = _make_file(claude_dir / "dst.txt", "original")
    status = safe_symlink(source, target, backup)
    assert status == "backed-up"
    assert target.is_symlink()
    backup_file = backup / ".claude" / "dst.txt"
    assert backup_file.is_file()
    assert backup_file.read_text() == "original"


def test_safe_symlink_backup_preserves_structure(
    home: Path, backup: Path, storage: Path, claude_dir: Path
) -> None:
    source = _make_file(storage / "lint.sh", "#!/bin/sh\n")
    target = _make_file(claude_dir / "hooks" / "lint.sh", "#old\n")
    safe_symlink(source, target, backup)
    assert (backup / ".claude" / "hooks" / "lint.sh").is_file()
    assert (backup / ".claude" / "hooks" / "lint.sh").read_text() == "#old\n"


def test_safe_symlink_creates_parent_dirs(
    home: Path, backup: Path, storage: Path
) -> None:
    source = _make_file(storage / "src.txt")
    target = home / ".claude" / "deeply" / "nested" / "dst.txt"
    safe_symlink(source, target, backup)
    assert target.is_symlink()


def test_safe_symlink_chmod_sh(home: Path, backup: Path, storage: Path) -> None:
    source = _make_file(storage / "run.sh", "#!/bin/sh\necho hi\n")
    # Strip exec bits to prove the function adds them.
    source.chmod(0o644)
    target = home / ".claude" / "hooks" / "run.sh"
    safe_symlink(source, target, backup)
    mode = source.stat().st_mode
    assert mode & stat.S_IXUSR
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH


# ── remove_symlink ────────────────────────────────────────────────────────


def test_remove_symlink_exists(home: Path, backup: Path, storage: Path) -> None:
    source = _make_file(storage / "src.txt")
    target = home / ".claude" / "dst.txt"
    safe_symlink(source, target, backup)
    assert remove_symlink(target) is True
    assert not target.exists()


def test_remove_symlink_not_symlink(home: Path) -> None:
    target = _make_file(home / "regular.txt", "keep")
    assert remove_symlink(target) is False
    assert target.is_file()
    assert target.read_text() == "keep"


def test_remove_symlink_missing(home: Path) -> None:
    assert remove_symlink(home / "nope.txt") is False


# ── is_managed_symlink ────────────────────────────────────────────────────


def test_is_managed_symlink_yes(home: Path, backup: Path, storage: Path) -> None:
    source = _make_file(storage / "src.txt")
    target = home / ".claude" / "dst.txt"
    safe_symlink(source, target, backup)
    assert is_managed_symlink(target, storage) is True


def test_is_managed_symlink_no(
    home: Path, backup: Path, storage: Path, tmp_path: Path
) -> None:
    outside = _make_file(tmp_path / "outside.txt")
    target = home / ".claude" / "dst.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(outside)
    assert is_managed_symlink(target, storage) is False

    # Regular file is also not managed.
    regular = _make_file(home / ".claude" / "regular.txt")
    assert is_managed_symlink(regular, storage) is False


# ── link_domain ───────────────────────────────────────────────────────────


def _make_domain(root: Path) -> Path:
    """Create a fake domain with skills/, agents/, rules/, hooks/."""
    domain = root / "my-domain"
    # skills/ contains subdirs.
    _make_file(domain / "skills" / "py-lint" / "SKILL.md", "s")
    _make_file(domain / "skills" / "README.md", "ignore")
    # agents/ contains .md files.
    _make_file(domain / "agents" / "reviewer.md", "a")
    # rules/ contains .md files.
    _make_file(domain / "rules" / "style.md", "r")
    # hooks/ contains .sh files + settings fragment to be skipped.
    sh = _make_file(domain / "hooks" / "lint.sh", "#!/bin/sh\n")
    sh.chmod(0o644)
    _make_file(domain / "hooks" / "settings.fragment.json", "{}")
    return domain


def test_link_domain_full(
    home: Path, backup: Path, storage: Path, claude_dir: Path
) -> None:
    domain = _make_domain(storage)
    messages = link_domain(domain, claude_dir, backup)
    assert (claude_dir / "skills" / "py-lint").is_symlink()
    assert (claude_dir / "agents" / "reviewer.md").is_symlink()
    assert (claude_dir / "rules" / "style.md").is_symlink()
    assert (claude_dir / "hooks" / "lint.sh").is_symlink()
    assert any(m.startswith("linked ") for m in messages)
    # .sh source got exec bits.
    src_sh = domain / "hooks" / "lint.sh"
    assert src_sh.stat().st_mode & stat.S_IXUSR


def test_link_domain_skips_readme(
    home: Path, backup: Path, storage: Path, claude_dir: Path
) -> None:
    domain = _make_domain(storage)
    link_domain(domain, claude_dir, backup)
    assert not (claude_dir / "skills" / "README.md").exists()


def test_link_domain_skips_settings_fragment(
    home: Path, backup: Path, storage: Path, claude_dir: Path
) -> None:
    domain = _make_domain(storage)
    link_domain(domain, claude_dir, backup)
    assert not (claude_dir / "hooks" / "settings.fragment.json").exists()


# ── link_standalone ───────────────────────────────────────────────────────


def test_link_standalone_skill(
    home: Path, backup: Path, storage: Path, claude_dir: Path
) -> None:
    skill = storage / "skills-cat" / "py-lint"
    _make_file(skill / "SKILL.md", "s")
    target = claude_dir / "skills" / "py-lint"
    status = link_standalone(skill, target, backup)
    assert status == "linked"
    assert target.is_symlink()
    assert target.resolve() == skill.resolve()


def test_link_standalone_agent(
    home: Path, backup: Path, storage: Path, claude_dir: Path
) -> None:
    agent = _make_file(storage / "agents-cat" / "reviewer.md", "a")
    target = claude_dir / "agents" / "reviewer.md"
    status = link_standalone(agent, target, backup)
    assert status == "linked"
    assert target.is_symlink()


# ── unlink_domain / unlink_standalone ─────────────────────────────────────


def test_unlink_domain(
    home: Path, backup: Path, storage: Path, claude_dir: Path
) -> None:
    domain = _make_domain(storage)
    link_domain(domain, claude_dir, backup)
    # Add an unrelated symlink that must NOT be removed.
    other = _make_file(storage / "other" / "x.md", "x")
    other_target = claude_dir / "agents" / "other.md"
    other_target.symlink_to(other)

    removed = unlink_domain(domain, claude_dir)
    assert "skills/py-lint" in removed
    assert "agents/reviewer.md" in removed
    assert "rules/style.md" in removed
    assert "hooks/lint.sh" in removed
    # Unrelated symlink survived.
    assert other_target.is_symlink()


def test_unlink_standalone(
    home: Path, backup: Path, storage: Path, claude_dir: Path
) -> None:
    agent = _make_file(storage / "agents-cat" / "reviewer.md", "a")
    target = claude_dir / "agents" / "reviewer.md"
    link_standalone(agent, target, backup)
    assert unlink_standalone(target) is True
    assert not target.exists()
    assert unlink_standalone(target) is False


# ── link_global_files ─────────────────────────────────────────────────────


def _make_global(root: Path) -> Path:
    g = root / "global"
    _make_file(g / "CLAUDE.md", "claude")
    _make_file(g / "settings.json", "{}")
    _make_file(g / "README.md", "ignore")
    sh = _make_file(g / "hooks" / "pre.sh", "#!/bin/sh\n")
    sh.chmod(0o644)
    _make_file(g / "hooks" / "README.md", "ignore")
    _make_file(g / "output-styles" / "style.md", "s")
    _make_file(g / "output-styles" / "README.md", "ignore")
    return g


def test_link_global_files(
    home: Path, backup: Path, storage: Path, claude_dir: Path
) -> None:
    g = _make_global(storage)
    messages = link_global_files(g, claude_dir, backup)
    assert (claude_dir / "CLAUDE.md").is_symlink()
    assert (claude_dir / "settings.json").is_symlink()
    assert (claude_dir / "hooks" / "pre.sh").is_symlink()
    assert (claude_dir / "output-styles" / "style.md").is_symlink()
    # .sh got chmod +x on the source.
    assert (g / "hooks" / "pre.sh").stat().st_mode & stat.S_IXUSR
    assert len(messages) == 4


def test_link_global_skips_readme(
    home: Path, backup: Path, storage: Path, claude_dir: Path
) -> None:
    g = _make_global(storage)
    link_global_files(g, claude_dir, backup)
    assert not (claude_dir / "README.md").exists()
    assert not (claude_dir / "hooks" / "README.md").exists()
    assert not (claude_dir / "output-styles" / "README.md").exists()


# ── sanity: os.readlink usage works on linked target ──────────────────────


def test_safe_symlink_relink_reads_existing_link(
    home: Path, backup: Path, storage: Path
) -> None:
    """Guard against regression in symlink introspection via os.readlink."""
    source = _make_file(storage / "src.txt")
    target = home / ".claude" / "dst.txt"
    safe_symlink(source, target, backup)
    # Manually inspect — ensures we can read it the same way the code does.
    assert Path(os.readlink(target)).resolve() == source.resolve()

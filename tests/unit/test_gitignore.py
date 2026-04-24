"""Unit tests for ai_dotfiles.core.gitignore."""

from __future__ import annotations

from pathlib import Path

from ai_dotfiles.core.gitignore import (
    MANAGED_END,
    MANAGED_START,
    collect_managed_paths,
    parse_blocks,
    render,
    sync_gitignore,
)

# ---------------------------------------------------------------------------
# collect_managed_paths
# ---------------------------------------------------------------------------


def _make_storage(tmp_path: Path) -> Path:
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "catalog").mkdir()
    return storage


def _make_claude(tmp_path: Path) -> Path:
    claude = tmp_path / "proj" / ".claude"
    claude.mkdir(parents=True)
    return claude


def test_collect_managed_paths_empty_claude_dir(tmp_path: Path) -> None:
    claude = _make_claude(tmp_path)
    storage = _make_storage(tmp_path)
    assert collect_managed_paths(claude, storage) == []


def test_collect_managed_paths_missing_claude_dir(tmp_path: Path) -> None:
    storage = _make_storage(tmp_path)
    assert collect_managed_paths(tmp_path / "nope", storage) == []


def test_collect_managed_paths_ignores_real_files(tmp_path: Path) -> None:
    claude = _make_claude(tmp_path)
    storage = _make_storage(tmp_path)
    skills = claude / "skills"
    skills.mkdir()
    (skills / "real.md").write_text("not a symlink", encoding="utf-8")
    assert collect_managed_paths(claude, storage) == []


def test_collect_managed_paths_ignores_symlinks_outside_storage(
    tmp_path: Path,
) -> None:
    claude = _make_claude(tmp_path)
    storage = _make_storage(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "target.md").write_text("x", encoding="utf-8")
    skills = claude / "skills"
    skills.mkdir()
    (skills / "user-link").symlink_to(outside / "target.md")
    assert collect_managed_paths(claude, storage) == []


def test_collect_managed_paths_returns_sorted_absolute_paths(
    tmp_path: Path,
) -> None:
    claude = _make_claude(tmp_path)
    storage = _make_storage(tmp_path)
    src_root = storage / "catalog" / "dom"
    (src_root / "skills" / "zebra").mkdir(parents=True)
    (src_root / "skills" / "alpha").mkdir(parents=True)
    (src_root / "agents").mkdir()
    (src_root / "agents" / "bot.md").write_text("x", encoding="utf-8")

    (claude / "skills").mkdir()
    (claude / "skills" / "zebra").symlink_to(src_root / "skills" / "zebra")
    (claude / "skills" / "alpha").symlink_to(src_root / "skills" / "alpha")
    (claude / "agents").mkdir()
    (claude / "agents" / "bot.md").symlink_to(src_root / "agents" / "bot.md")

    paths = collect_managed_paths(claude, storage)
    assert paths == [
        "/.claude/agents/bot.md",
        "/.claude/skills/alpha",
        "/.claude/skills/zebra",
    ]


def test_collect_managed_paths_picks_up_top_level_claude_md_symlink(
    tmp_path: Path,
) -> None:
    claude = _make_claude(tmp_path)
    storage = _make_storage(tmp_path)
    src = storage / "global" / "CLAUDE.md"
    src.parent.mkdir(parents=True)
    src.write_text("x", encoding="utf-8")
    (claude / "CLAUDE.md").symlink_to(src)
    assert collect_managed_paths(claude, storage) == ["/.claude/CLAUDE.md"]


# ---------------------------------------------------------------------------
# parse_blocks / render
# ---------------------------------------------------------------------------


def test_parse_blocks_no_markers() -> None:
    text = "node_modules/\n*.log\n"
    before, managed, after = parse_blocks(text)
    assert before == ["node_modules/", "*.log"]
    assert managed == []
    assert after == []


def test_parse_blocks_round_trip() -> None:
    text = "\n".join(
        [
            "node_modules/",
            MANAGED_START,
            "/.claude/skills/a",
            "/.claude/skills/b",
            MANAGED_END,
            "*.log",
        ]
    )
    before, managed, after = parse_blocks(text)
    assert before == ["node_modules/"]
    assert managed == ["/.claude/skills/a", "/.claude/skills/b"]
    assert after == ["*.log"]


def test_parse_blocks_unclosed_block_treated_as_no_block() -> None:
    text = "foo\n" + MANAGED_START + "\nbar\n"
    before, managed, after = parse_blocks(text)
    # Malformed — parse refuses to truncate user content.
    assert managed == []
    assert after == []
    assert before == ["foo", MANAGED_START, "bar"]


def test_render_omits_markers_when_managed_empty() -> None:
    out = render(["foo", "bar"], [], [])
    assert MANAGED_START not in out
    assert MANAGED_END not in out
    assert out == "foo\nbar\n"


def test_render_empty_input_returns_empty_string() -> None:
    assert render([], [], []) == ""
    assert render([""], [], [""]) == ""


def test_render_includes_markers_when_managed_non_empty() -> None:
    out = render(["user"], ["/.claude/skills/a"], ["other"])
    lines = out.splitlines()
    assert lines[0] == "user"
    assert lines[1] == MANAGED_START
    assert lines[2] == "/.claude/skills/a"
    assert lines[3] == MANAGED_END
    assert lines[4] == "other"


# ---------------------------------------------------------------------------
# sync_gitignore
# ---------------------------------------------------------------------------


def test_sync_creates_gitignore_when_git_dir_present(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    wrote = sync_gitignore(root, ["/.claude/skills/a"])
    assert wrote is True
    assert (root / ".gitignore").read_text(encoding="utf-8").startswith(
        MANAGED_START + "\n"
    ) or MANAGED_START in (root / ".gitignore").read_text(encoding="utf-8")


def test_sync_skips_when_no_git_and_no_gitignore(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    assert sync_gitignore(root, ["/.claude/skills/a"]) is False
    assert not (root / ".gitignore").exists()


def test_sync_manages_when_gitignore_present_without_git(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    assert sync_gitignore(root, ["/.claude/skills/a"]) is True
    text = (root / ".gitignore").read_text(encoding="utf-8")
    assert "node_modules/" in text
    assert "/.claude/skills/a" in text


def test_sync_preserves_user_authored_lines_outside_block(
    tmp_path: Path,
) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    (root / ".gitignore").write_text("node_modules/\n*.log\n", encoding="utf-8")
    sync_gitignore(root, ["/.claude/skills/a"])
    text = (root / ".gitignore").read_text(encoding="utf-8")
    assert "node_modules/" in text
    assert "*.log" in text
    assert "/.claude/skills/a" in text


def test_sync_replaces_existing_block(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    initial = "\n".join(
        [
            "user1",
            MANAGED_START,
            "/.claude/skills/old",
            MANAGED_END,
            "user2",
            "",
        ]
    )
    (root / ".gitignore").write_text(initial, encoding="utf-8")
    sync_gitignore(root, ["/.claude/skills/new"])
    text = (root / ".gitignore").read_text(encoding="utf-8")
    assert "/.claude/skills/new" in text
    assert "/.claude/skills/old" not in text
    assert "user1" in text and "user2" in text


def test_sync_removes_block_when_managed_empty(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    initial = "\n".join(
        [
            "user1",
            MANAGED_START,
            "/.claude/skills/old",
            MANAGED_END,
            "user2",
            "",
        ]
    )
    (root / ".gitignore").write_text(initial, encoding="utf-8")
    sync_gitignore(root, [])
    text = (root / ".gitignore").read_text(encoding="utf-8")
    assert MANAGED_START not in text
    assert MANAGED_END not in text
    assert "user1" in text and "user2" in text


def test_sync_skips_paths_already_in_user_authored_lines(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    (root / ".gitignore").write_text("/.claude/skills/a\n", encoding="utf-8")
    sync_gitignore(root, ["/.claude/skills/a", "/.claude/skills/b"])
    text = (root / ".gitignore").read_text(encoding="utf-8")
    # Only the non-colliding path ends up inside the block.
    before, managed, _after = parse_blocks(text)
    assert "/.claude/skills/a" not in managed
    assert "/.claude/skills/b" in managed
    # User-authored line survives.
    assert "/.claude/skills/a" in before


def test_sync_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    paths = ["/.claude/skills/a", "/.claude/agents/x.md"]
    assert sync_gitignore(root, paths) is True
    bytes_first = (root / ".gitignore").read_bytes()
    assert sync_gitignore(root, paths) is False
    assert (root / ".gitignore").read_bytes() == bytes_first


def test_sync_noop_when_no_block_and_nothing_to_add(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    (root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    # No managed paths to add; existing file is already canonical.
    assert sync_gitignore(root, []) is False
    assert (root / ".gitignore").read_text(encoding="utf-8") == "node_modules/\n"

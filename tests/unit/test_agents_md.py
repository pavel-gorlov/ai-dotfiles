"""Unit tests for ai_dotfiles.core.agents_md."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_dotfiles.core.agents_md import (
    AGENTS_FILENAME,
    block_markers,
    iter_rule_block_names,
    rule_block_targets,
    rule_name_of,
    strip_rule_blocks,
    upsert_rule_block,
)
from ai_dotfiles.core.errors import ElementError


def _write_rule(directory: Path, name: str, frontmatter: str, body: str) -> Path:
    """Write a rule markdown file with raw frontmatter and body."""
    path = directory / f"{name}.md"
    path.write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")
    return path


# --- rule_name_of -----------------------------------------------------


def test_rule_name_of_uses_stem(tmp_path: Path) -> None:
    assert rule_name_of(tmp_path / "python.md") == "python"


def test_rule_name_of_rejects_unsafe_name(tmp_path: Path) -> None:
    with pytest.raises(ElementError):
        rule_name_of(tmp_path / "bad name.md")


# --- block_markers ----------------------------------------------------


def test_block_markers_shape() -> None:
    start, end = block_markers("python")
    assert start == "<!-- ai-dotfiles:rule:python START -->"
    assert end == "<!-- ai-dotfiles:rule:python END -->"


# --- upsert_rule_block: write to root --------------------------------


def test_upsert_writes_block_to_new_file(tmp_path: Path) -> None:
    agents = tmp_path / AGENTS_FILENAME
    wrote = upsert_rule_block(agents, "python", "Rule body line.")

    assert wrote is True
    text = agents.read_text(encoding="utf-8")
    start, end = block_markers("python")
    assert start in text
    assert end in text
    assert "Rule body line." in text


def test_upsert_creates_parent_dirs(tmp_path: Path) -> None:
    agents = tmp_path / "src" / "api" / AGENTS_FILENAME
    upsert_rule_block(agents, "scoped", "Scoped body.")
    assert agents.is_file()
    assert "Scoped body." in agents.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "glob_dir",
    ["**", "*.py", "tests/e2e/**", "file[0-9]", "log?"],
)
def test_upsert_refuses_glob_named_directory(tmp_path: Path, glob_dir: str) -> None:
    """``upsert_rule_block`` must never ``mkdir`` a glob-named directory (ai-18)."""
    agents = tmp_path / glob_dir / AGENTS_FILENAME
    with pytest.raises(ElementError, match="glob-named directory"):
        upsert_rule_block(agents, "scoped", "Scoped body.")
    # Nothing was created.
    assert not agents.exists()
    assert not agents.parent.exists()


# --- idempotency ------------------------------------------------------


def test_upsert_is_idempotent_on_unchanged_body(tmp_path: Path) -> None:
    agents = tmp_path / AGENTS_FILENAME
    assert upsert_rule_block(agents, "python", "Body.") is True
    first = agents.read_text(encoding="utf-8")

    # Re-running with the same body is a no-op — no rewrite, no drift.
    assert upsert_rule_block(agents, "python", "Body.") is False
    assert agents.read_text(encoding="utf-8") == first


def test_upsert_no_duplicate_blocks_on_rerun(tmp_path: Path) -> None:
    agents = tmp_path / AGENTS_FILENAME
    upsert_rule_block(agents, "python", "Body.")
    upsert_rule_block(agents, "python", "Body.")
    assert iter_rule_block_names(agents.read_text(encoding="utf-8")) == ["python"]


def test_upsert_updates_changed_body_in_place(tmp_path: Path) -> None:
    agents = tmp_path / AGENTS_FILENAME
    upsert_rule_block(agents, "python", "Old body.")
    assert upsert_rule_block(agents, "python", "New body.") is True

    text = agents.read_text(encoding="utf-8")
    assert "New body." in text
    assert "Old body." not in text
    assert iter_rule_block_names(text) == ["python"]


def test_upsert_multiple_rules_coexist(tmp_path: Path) -> None:
    agents = tmp_path / AGENTS_FILENAME
    upsert_rule_block(agents, "python", "Python body.")
    upsert_rule_block(agents, "gitflow", "Gitflow body.")
    assert iter_rule_block_names(agents.read_text(encoding="utf-8")) == [
        "python",
        "gitflow",
    ]


# --- strip ------------------------------------------------------------


def test_strip_removes_all_managed_blocks(tmp_path: Path) -> None:
    agents = tmp_path / AGENTS_FILENAME
    upsert_rule_block(agents, "python", "Python body.")
    upsert_rule_block(agents, "gitflow", "Gitflow body.")

    stripped = strip_rule_blocks(agents.read_text(encoding="utf-8"))
    assert "ai-dotfiles:rule" not in stripped
    assert stripped.strip() == ""


def test_strip_named_subset_keeps_others(tmp_path: Path) -> None:
    agents = tmp_path / AGENTS_FILENAME
    upsert_rule_block(agents, "python", "Python body.")
    upsert_rule_block(agents, "gitflow", "Gitflow body.")

    stripped = strip_rule_blocks(agents.read_text(encoding="utf-8"), {"python"})
    assert iter_rule_block_names(stripped) == ["gitflow"]
    assert "Python body." not in stripped
    assert "Gitflow body." in stripped


# --- user-text preservation ------------------------------------------


def test_upsert_preserves_user_text(tmp_path: Path) -> None:
    agents = tmp_path / AGENTS_FILENAME
    agents.write_text(
        "# Project AGENTS\n\nHand-written guidance for Codex.\n",
        encoding="utf-8",
    )
    upsert_rule_block(agents, "python", "Managed body.")

    text = agents.read_text(encoding="utf-8")
    assert "# Project AGENTS" in text
    assert "Hand-written guidance for Codex." in text
    assert "Managed body." in text


def test_strip_preserves_user_text_in_mixed_file(tmp_path: Path) -> None:
    agents = tmp_path / AGENTS_FILENAME
    agents.write_text("# Heading\n\nUser paragraph.\n", encoding="utf-8")
    upsert_rule_block(agents, "python", "Managed body.")
    upsert_rule_block(agents, "gitflow", "Another managed body.")

    stripped = strip_rule_blocks(agents.read_text(encoding="utf-8"))
    assert "# Heading" in stripped
    assert "User paragraph." in stripped
    assert "ai-dotfiles:rule" not in stripped
    # No runaway blank lines after removing the blocks.
    assert "\n\n\n" not in stripped


def test_strip_then_upsert_roundtrip_is_stable(tmp_path: Path) -> None:
    agents = tmp_path / AGENTS_FILENAME
    agents.write_text("# Heading\n\nUser text.\n", encoding="utf-8")
    upsert_rule_block(agents, "python", "Body.")
    after_first = agents.read_text(encoding="utf-8")

    # strip + re-upsert reproduces the same file — no drift.
    rebuilt = strip_rule_blocks(after_first, {"python"})
    agents.write_text(rebuilt, encoding="utf-8")
    upsert_rule_block(agents, "python", "Body.")
    assert agents.read_text(encoding="utf-8") == after_first


# --- iter_rule_block_names -------------------------------------------


def test_iter_rule_block_names_empty_for_plain_file() -> None:
    assert iter_rule_block_names("# Just a heading\n\ntext\n") == []


# --- rule_block_targets: always-on -----------------------------------


def test_rule_block_targets_always_on(tmp_path: Path) -> None:
    rule = _write_rule(tmp_path, "base", "always_on: true", "Base rule.")
    targets = rule_block_targets(rule, tmp_path, "always_on")
    assert targets == [tmp_path / AGENTS_FILENAME]


# --- rule_block_targets: path-scoped ---------------------------------


def test_rule_block_targets_path_scoped_nested_dirs(tmp_path: Path) -> None:
    rule = _write_rule(
        tmp_path, "scoped", 'paths: ["src/api", "tests"]', "Scoped rule."
    )
    targets = rule_block_targets(rule, tmp_path, "path_scoped")
    assert targets == [
        (tmp_path / "src" / "api" / AGENTS_FILENAME).resolve(),
        (tmp_path / "tests" / AGENTS_FILENAME).resolve(),
    ]


def test_rule_block_targets_path_scoped_dedupes(tmp_path: Path) -> None:
    # Two literal entries resolving to the same directory dedupe.
    rule = _write_rule(tmp_path, "scoped", 'paths: ["src", "./src"]', "Scoped rule.")
    targets = rule_block_targets(rule, tmp_path, "path_scoped")
    assert targets == [(tmp_path / "src" / AGENTS_FILENAME).resolve()]


# --- rule_block_targets: glob entries are rejected (ai-18) -----------


@pytest.mark.parametrize(
    "paths_fm",
    [
        'paths: ["**/*.py"]',  # all-glob, real catalog shape
        'paths: ["src/**", "lib/*"]',  # trailing-glob — used to be "stripped"
        'paths: ["backend", "**/*.spec.ts"]',  # mixed dir + glob
        'paths: ["data/file[0-9].txt"]',  # bracket glob
    ],
)
def test_rule_block_targets_rejects_glob_entry(tmp_path: Path, paths_fm: str) -> None:
    """A glob ``paths:`` entry has no AGENTS.md surface — reject, never mkdir.

    Defence in depth: the classifier already demotes such rules to
    description-only, but ``rule_block_targets`` must refuse a glob entry
    even if mis-called, so it can never resolve a literal-glob directory.
    """
    rule = _write_rule(tmp_path, "scoped", paths_fm, "Scoped rule.")
    with pytest.raises(ElementError, match="no AGENTS.md surface"):
        rule_block_targets(rule, tmp_path, "path_scoped")


def test_rule_block_targets_path_scoped_missing_paths_raises(tmp_path: Path) -> None:
    rule = _write_rule(tmp_path, "broken", "always_on: false", "No paths.")
    with pytest.raises(ElementError):
        rule_block_targets(rule, tmp_path, "path_scoped")


def test_rule_block_targets_description_only_raises(tmp_path: Path) -> None:
    rule = _write_rule(tmp_path, "desc", "always_on: false", "Desc rule.")
    with pytest.raises(ElementError):
        rule_block_targets(rule, tmp_path, "description_only")


def test_rule_block_targets_unknown_class_raises(tmp_path: Path) -> None:
    rule = _write_rule(tmp_path, "x", "always_on: true", "x")
    with pytest.raises(ElementError):
        rule_block_targets(rule, tmp_path, "bogus")


# --- end-to-end: classified rule body lands in AGENTS.md -------------


def test_always_on_rule_body_lands_in_root_agents_md(tmp_path: Path) -> None:
    rule = _write_rule(tmp_path, "base", "always_on: true", "Always-on guidance.")
    (target,) = rule_block_targets(rule, tmp_path, "always_on")
    body = rule.read_text(encoding="utf-8").split("---\n", 2)[2].strip()
    upsert_rule_block(target, rule_name_of(rule), body)

    text = target.read_text(encoding="utf-8")
    assert target == tmp_path / AGENTS_FILENAME
    assert "Always-on guidance." in text
    # Frontmatter must not leak into the managed block.
    assert "always_on: true" not in text


def test_path_scoped_rule_body_lands_in_each_dir(tmp_path: Path) -> None:
    rule = _write_rule(tmp_path, "py", 'paths: ["src", "tests"]', "Scoped guidance.")
    name = rule_name_of(rule)
    body = rule.read_text(encoding="utf-8").split("---\n", 2)[2].strip()
    for target in rule_block_targets(rule, tmp_path, "path_scoped"):
        upsert_rule_block(target, name, body)

    for sub in ("src", "tests"):
        text = (tmp_path / sub / AGENTS_FILENAME).read_text(encoding="utf-8")
        assert "Scoped guidance." in text
        assert iter_rule_block_names(text) == ["py"]

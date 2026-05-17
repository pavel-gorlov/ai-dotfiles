"""Unit tests for ai_dotfiles.core.rule_classify."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_dotfiles.core.errors import ElementError
from ai_dotfiles.core.rule_classify import RuleClass, classify_rule


def _write_rule(directory: Path, name: str, frontmatter: str, body: str = "") -> Path:
    """Write a rule markdown file with the given raw frontmatter block."""
    path = directory / f"{name}.md"
    text = f"---\n{frontmatter}\n---\n\n{body}"
    path.write_text(text, encoding="utf-8")
    return path


def test_rule_class_values() -> None:
    assert RuleClass.ALWAYS_ON.value == "always_on"
    assert RuleClass.PATH_SCOPED.value == "path_scoped"
    assert RuleClass.DESCRIPTION_ONLY.value == "description_only"


def test_path_scoped_inline_list(tmp_path: Path) -> None:
    # All entries are literal, glob-free directories.
    path = _write_rule(tmp_path, "scoped", 'paths: ["backend", "apps/web/src"]')
    assert classify_rule(path) is RuleClass.PATH_SCOPED


def test_path_scoped_block_list(tmp_path: Path) -> None:
    path = _write_rule(tmp_path, "scoped", "paths:\n  - src\n  - tests")
    assert classify_rule(path) is RuleClass.PATH_SCOPED


# --- glob paths: are NOT path-scoped (ai-18) -------------------------


def test_all_glob_paths_is_description_only(tmp_path: Path) -> None:
    # The real catalog shape: a file-type glob. Codex has no
    # file-glob-scoped AGENTS.md surface — demote to description-only.
    path = _write_rule(tmp_path, "fastapi", 'paths: ["**/*.py"]')
    assert classify_rule(path) is RuleClass.DESCRIPTION_ONLY


def test_mixed_glob_and_dir_paths_is_description_only(tmp_path: Path) -> None:
    # All-or-nothing: one glob entry demotes the whole rule. Never
    # half-apply (some dirs as AGENTS.md, some globs dropped).
    path = _write_rule(
        tmp_path, "playwright", "paths:\n  - '**/tests/e2e'\n  - '**/*.spec.ts'"
    )
    assert classify_rule(path) is RuleClass.DESCRIPTION_ONLY


@pytest.mark.parametrize(
    "entry",
    ["**/*.tsx", "**/playwright.config.ts", "src/**", "lib/*", "data/file[0-9].txt"],
)
def test_single_glob_entry_demotes_rule(tmp_path: Path, entry: str) -> None:
    path = _write_rule(tmp_path, "g", f"paths:\n  - '{entry}'")
    assert classify_rule(path) is RuleClass.DESCRIPTION_ONLY


def test_glob_paths_with_always_on_falls_through_to_always_on(tmp_path: Path) -> None:
    # A glob paths: has no AGENTS.md surface, so it does not win; the
    # explicit always_on then applies.
    path = _write_rule(tmp_path, "mix", 'paths: ["**/*.py"]\nalways_on: true')
    assert classify_rule(path) is RuleClass.ALWAYS_ON


def test_always_on_true(tmp_path: Path) -> None:
    path = _write_rule(tmp_path, "base", "always_on: true")
    assert classify_rule(path) is RuleClass.ALWAYS_ON


@pytest.mark.parametrize("spelling", ["true", "True", "yes", "1"])
def test_always_on_truthy_spellings(tmp_path: Path, spelling: str) -> None:
    path = _write_rule(tmp_path, "base", f"always_on: {spelling}")
    assert classify_rule(path) is RuleClass.ALWAYS_ON


def test_always_on_false_is_description_only(tmp_path: Path) -> None:
    path = _write_rule(tmp_path, "base", "always_on: false")
    assert classify_rule(path) is RuleClass.DESCRIPTION_ONLY


def test_description_only_when_neither_field(tmp_path: Path) -> None:
    # The default for every un-migrated catalog rule.
    path = _write_rule(tmp_path, "plain", "name: plain\ndescription: A rule.")
    assert classify_rule(path) is RuleClass.DESCRIPTION_ONLY


def test_empty_paths_list_is_not_path_scoped(tmp_path: Path) -> None:
    # An empty `paths: []` is not a scope — falls through to default.
    path = _write_rule(tmp_path, "empty", "paths: []")
    assert classify_rule(path) is RuleClass.DESCRIPTION_ONLY


def test_empty_paths_with_always_on_is_always_on(tmp_path: Path) -> None:
    # Empty `paths:` does not win; `always_on: true` then applies.
    path = _write_rule(tmp_path, "mix", "paths: []\nalways_on: true")
    assert classify_rule(path) is RuleClass.ALWAYS_ON


def test_paths_wins_over_always_on(tmp_path: Path) -> None:
    # Both present and `paths:` non-empty *and* all glob-free dirs: a
    # path-scoped rule is inherently conditional, so PATH_SCOPED wins.
    path = _write_rule(tmp_path, "both", 'paths: ["src"]\nalways_on: true')
    assert classify_rule(path) is RuleClass.PATH_SCOPED


def test_missing_frontmatter_is_description_only(tmp_path: Path) -> None:
    path = tmp_path / "no-fm.md"
    path.write_text("# A rule with no frontmatter\n\nJust prose.", encoding="utf-8")
    assert classify_rule(path) is RuleClass.DESCRIPTION_ONLY


def test_always_loaded_prose_is_not_inferred(tmp_path: Path) -> None:
    # Explicit beats heuristic: "Always-loaded" in the body must NOT
    # promote the rule to ALWAYS_ON without the explicit field.
    path = _write_rule(
        tmp_path,
        "prosey",
        "name: prosey",
        body="# Title\n\nAlways-loaded baseline of how the agent works.",
    )
    assert classify_rule(path) is RuleClass.DESCRIPTION_ONLY


def test_missing_file_raises_element_error(tmp_path: Path) -> None:
    with pytest.raises(ElementError, match="Rule file not found"):
        classify_rule(tmp_path / "does-not-exist.md")


def test_directory_path_raises_element_error(tmp_path: Path) -> None:
    with pytest.raises(ElementError, match="Rule file not found"):
        classify_rule(tmp_path)

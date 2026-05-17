"""Unit tests for ai_dotfiles.core.frontmatter."""

from __future__ import annotations

import pytest

from ai_dotfiles.core.frontmatter import parse_frontmatter


def test_no_frontmatter_returns_empty() -> None:
    assert parse_frontmatter("# Just a heading\n\nbody text") == {}


def test_empty_string_returns_empty() -> None:
    assert parse_frontmatter("") == {}


def test_scalar_values() -> None:
    text = "---\nname: commit\ndescription: Write a commit.\n---\nbody\n"
    assert parse_frontmatter(text) == {
        "name": "commit",
        "description": "Write a commit.",
    }


def test_quoted_scalar_is_unquoted() -> None:
    text = "---\nname: \"commit\"\ndesc: 'single'\n---\nbody\n"
    parsed = parse_frontmatter(text)
    assert parsed["name"] == "commit"
    assert parsed["desc"] == "single"


def test_inline_list() -> None:
    text = '---\ndepends: ["@python", "skill:x"]\n---\nbody\n'
    assert parse_frontmatter(text)["depends"] == ["@python", "skill:x"]


def test_empty_inline_list() -> None:
    text = "---\ndepends: []\n---\nbody\n"
    assert parse_frontmatter(text)["depends"] == []


def test_block_list() -> None:
    text = '---\ndepends:\n  - "@python"\n  - skill:x\n---\nbody\n'
    assert parse_frontmatter(text)["depends"] == ["@python", "skill:x"]


def test_block_list_terminated_by_next_key() -> None:
    text = "---\ndepends:\n  - skill:a\nname: foo\n---\nbody\n"
    parsed = parse_frontmatter(text)
    assert parsed["depends"] == ["skill:a"]
    assert parsed["name"] == "foo"


def test_block_list_with_blank_lines() -> None:
    text = "---\ndepends:\n  - skill:a\n\n  - skill:b\n---\nbody\n"
    assert parse_frontmatter(text)["depends"] == ["skill:a", "skill:b"]


def test_missing_key_absent_from_result() -> None:
    text = "---\nname: foo\n---\nbody\n"
    assert "depends" not in parse_frontmatter(text)


def test_comment_lines_ignored() -> None:
    text = "---\n# a comment\nname: foo\n---\nbody\n"
    assert parse_frontmatter(text) == {"name": "foo"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("---\ndepends: [a]\n---\nx\n", ["a"]),
        ("---\ndepends: [ a , b ]\n---\nx\n", ["a", "b"]),
        ("---\ndepends: [\"a\", b, 'c']\n---\nx\n", ["a", "b", "c"]),
    ],
)
def test_inline_list_variants(text: str, expected: list[str]) -> None:
    assert parse_frontmatter(text)["depends"] == expected

"""Minimal YAML-frontmatter parser for catalog elements.

ai-dotfiles does not ship PyYAML as a runtime dependency. Catalog
elements (skills, agents, rules) carry a small YAML frontmatter block
at the top of a markdown file::

    ---
    name: commit
    description: Write a Conventional Commit.
    depends: ["@gitflow", "skill:x"]
    ---

This module extracts *just enough* YAML to cover the shapes the catalog
actually uses: top-level scalar values and lists (inline ``[a, b]`` or
block ``- a`` form). Anything more elaborate (anchors, multi-line
strings, nested mappings) is intentionally unsupported.

:func:`parse_frontmatter` is the single shared entry point — other
``core/`` modules import it instead of re-implementing the parser.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["parse_frontmatter"]

# Matches the leading ``---\n ... \n---\n`` block of a markdown file.
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# A top-level ``key: value`` (possibly with an empty value for a block list).
_KEY_RE = re.compile(r"^(?P<key>[A-Za-z0-9_-]+)\s*:\s*(?P<value>.*?)\s*$")
# A block-list item line: indented ``- item``.
_BLOCK_ITEM_RE = re.compile(r"^\s+-\s*(?P<item>.+?)\s*$")
# Any non-indented line starts a new top-level key (or terminates a block).
_TOP_LEVEL_RE = re.compile(r"^\S")


def _strip_quotes(token: str) -> str:
    """Strip a single matching pair of surrounding quotes from ``token``."""
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token


def _parse_inline_list(raw: str) -> list[str]:
    """Parse an inline ``[a, b, c]`` list body (without the brackets)."""
    inner = raw.strip()[1:-1]
    if not inner.strip():
        return []
    return [_strip_quotes(part) for part in inner.split(",") if part.strip()]


def parse_frontmatter(text: str) -> dict[str, Any]:
    """Parse the YAML frontmatter block of ``text`` into a dict.

    Returns an empty dict if ``text`` has no frontmatter block. Values
    are either strings (scalars) or ``list[str]`` (inline or block
    lists). Quotes around scalar tokens and list items are stripped.

    Only top-level keys are recognised; nested mappings are ignored.
    """
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return {}

    result: dict[str, Any] = {}
    lines = match.group(1).splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key_match = _KEY_RE.match(line)
        if key_match is None:
            continue
        key = key_match.group("key")
        value = key_match.group("value")

        if value.startswith("[") and value.endswith("]"):
            result[key] = _parse_inline_list(value)
            continue
        if value:
            result[key] = _strip_quotes(value)
            continue

        # Empty value — a block list may follow on subsequent indented lines.
        items: list[str] = []
        while index < len(lines):
            following = lines[index]
            if not following.strip():
                index += 1
                continue
            if _TOP_LEVEL_RE.match(following):
                break
            item_match = _BLOCK_ITEM_RE.match(following)
            if item_match is not None:
                items.append(_strip_quotes(item_match.group("item")))
            index += 1
        result[key] = items
    return result

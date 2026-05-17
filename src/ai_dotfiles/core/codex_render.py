"""Pure render transforms for the Codex CLI target.

A catalog element is a markdown file with YAML frontmatter. The Codex
target wants two different on-disk shapes:

* a catalog *agent* ``.md`` becomes a Codex ``.toml`` (frontmatter keys
  ``name`` / ``description`` / optional ``model`` plus the markdown body
  as ``developer_instructions``);
* a catalog ``SKILL.md`` is re-emitted with its ``description`` trimmed
  to a single sentence (ADR ai-1-4).

Both outputs carry a two-line drift-detection header (ADR ai-1-1) — a
``# managed-by`` marker and the SHA-256 of the *source* file's content.

The two public functions are pure string transforms: they take a path,
read it, and return a string. They do no writing and no symlinking —
that is the command/install layer's job (ai-5).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import tomli_w

from ai_dotfiles.core.errors import ElementError
from ai_dotfiles.core.frontmatter import parse_frontmatter

__all__ = [
    "render_agent_toml",
    "render_rule_skill_md",
    "render_skill_md",
    "split_body",
]

# Same leading ``---\n ... \n---\n`` block matched by the frontmatter
# parser; reused here to split the body from the frontmatter.
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# A sentence ends at the first ``.``, ``!`` or ``?`` followed by
# whitespace or end-of-string. Used to trim a skill description.
_SENTENCE_END_RE = re.compile(r"[.!?](?=\s|$)")

_MANAGED_BY = "# managed-by: ai-dotfiles"


def _source_sha256(text: str) -> str:
    """Return the hex SHA-256 of ``text`` encoded as UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _header(source_text: str) -> str:
    """Build the two-line managed-by + source-sha256 drift header."""
    return f"{_MANAGED_BY}\n# source-sha256: {_source_sha256(source_text)}\n"


def split_body(text: str) -> str:
    """Return the markdown body of ``text`` (everything after frontmatter).

    A catalog element is ``---\\n<yaml>\\n---\\n<body>``; this strips the
    leading frontmatter block and returns the trimmed body. Text with no
    frontmatter is returned trimmed unchanged. Shared by the Codex apply
    layer (ai-11) so the body-extraction rule has a single home.
    """
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return text.strip()
    return text[match.end() :].strip()


def _first_sentence(description: str) -> str:
    """Trim ``description`` to its first sentence (ADR ai-1-4).

    Trailing trigger phrases are dropped. The sentence-terminating
    punctuation is kept; if no terminator is found the whole string is
    returned unchanged.
    """
    description = description.strip()
    match = _SENTENCE_END_RE.search(description)
    if match is None:
        return description
    return description[: match.end()].strip()


def render_agent_toml(md_path: Path) -> str:
    """Render a catalog agent ``.md`` into Codex ``.toml`` form.

    The frontmatter ``name`` and ``description`` become TOML keys, the
    markdown body becomes ``developer_instructions``, and ``model`` is
    emitted only when present in the frontmatter. The result is prefixed
    with the managed-by + source-sha256 header (ADR ai-1-1).

    Raises:
        ElementError: if the agent frontmatter lacks ``name`` or
            ``description``.
    """
    source_text = md_path.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(source_text)

    name = frontmatter.get("name")
    description = frontmatter.get("description")
    if not isinstance(name, str) or not name:
        raise ElementError(f"agent {md_path} has no 'name' in frontmatter")
    if not isinstance(description, str) or not description:
        raise ElementError(f"agent {md_path} has no 'description' in frontmatter")

    table: dict[str, Any] = {
        "name": name,
        "description": description,
        "developer_instructions": split_body(source_text),
    }
    model = frontmatter.get("model")
    if isinstance(model, str) and model:
        table["model"] = model

    # tomli-w emits no comments, so the drift header is prepended raw.
    return _header(source_text) + tomli_w.dumps(table)


def render_skill_md(md_path: Path) -> str:
    """Re-emit a catalog ``SKILL.md`` for the Codex target.

    The ``description`` frontmatter field is trimmed to its first
    sentence (ADR ai-1-4); every other frontmatter field and the
    markdown body are preserved verbatim. The managed-by +
    source-sha256 header (ADR ai-1-1) is prepended.

    Raises:
        ElementError: if the skill has no frontmatter ``description``.
    """
    source_text = md_path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(source_text)
    if match is None:
        raise ElementError(f"skill {md_path} has no frontmatter block")

    frontmatter_block = match.group(1)
    frontmatter = parse_frontmatter(source_text)
    description = frontmatter.get("description")
    if not isinstance(description, str) or not description:
        raise ElementError(f"skill {md_path} has no 'description' in frontmatter")

    trimmed = _trim_description_line(frontmatter_block, description)
    body = source_text[match.end() :]

    return f"{_header(source_text)}---\n{trimmed}\n---\n{body}"


def _rule_skill_description(rule_md: Path, body: str) -> str:
    """Derive a one-sentence ``description`` for a synthetic rule skill.

    A catalog rule rarely carries a ``description`` frontmatter field, so
    the description is taken (in priority order) from an explicit
    frontmatter ``description``, then the first non-heading sentence of
    the rule body, and finally a generic fallback naming the rule.
    """
    explicit = parse_frontmatter(rule_md.read_text(encoding="utf-8")).get("description")
    if isinstance(explicit, str) and explicit.strip():
        return _first_sentence(explicit)

    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return _first_sentence(stripped)

    return f"Project rule: {rule_md.stem}."


def render_rule_skill_md(rule_md: Path) -> str:
    """Render a description-only catalog rule as a Codex-only skill.

    ADR ai-1-2: a rule that is neither always-on nor path-scoped maps
    onto a synthetic Codex skill named ``rule-<stem>``. Catalog rules
    have no ``SKILL.md`` shape (often no frontmatter at all), so this
    synthesises ``name`` / ``description`` frontmatter — the description
    trimmed to one sentence (ADR ai-1-4) — and keeps the rule body. The
    managed-by + source-sha256 header (ADR ai-1-1) keys off the rule's
    own content so drift detection works exactly as for a real skill.
    """
    source_text = rule_md.read_text(encoding="utf-8")
    body = split_body(source_text)
    description = _rule_skill_description(rule_md, body)
    escaped = description.replace("\\", "\\\\").replace('"', '\\"')
    name = f"rule-{rule_md.stem}"

    return (
        f"{_header(source_text)}"
        f'---\nname: {name}\ndescription: "{escaped}"\n---\n\n{body}\n'
    )


def _trim_description_line(frontmatter_block: str, description: str) -> str:
    """Return ``frontmatter_block`` with the ``description`` value trimmed.

    The original line is located by key and replaced with a single
    double-quoted line holding the first-sentence description. A
    multi-line block-scalar description occupies several source lines;
    those continuation lines are dropped.
    """
    trimmed = _first_sentence(description)
    escaped = trimmed.replace("\\", "\\\\").replace('"', '\\"')
    lines = frontmatter_block.splitlines()
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if re.match(r"^description\s*:", line):
            out.append(f'description: "{escaped}"')
            index += 1
            # Skip any indented continuation lines of the old value.
            while index < len(lines) and (
                not lines[index].strip() or lines[index][:1] in (" ", "\t")
            ):
                index += 1
            continue
        out.append(line)
        index += 1
    return "\n".join(out)

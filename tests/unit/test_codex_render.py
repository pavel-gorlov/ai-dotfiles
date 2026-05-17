"""Unit tests for ai_dotfiles.core.codex_render."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import tomllib

from ai_dotfiles.core.codex_render import render_agent_toml, render_skill_md
from ai_dotfiles.core.errors import ElementError

_AGENT_MD = """\
---
name: example-agent
description: An example agent demonstrating frontmatter
model: opus
---

# Example Agent

Body line one.

## Instructions

You are a specialized agent that does things.
"""

_AGENT_NO_MODEL = """\
---
name: plain-agent
description: An agent with no model field
---

# Plain Agent

Just a body.
"""

_SKILL_MD = """\
---
name: commit
description: Write a Conventional Commit. Trigger on EN 'commit'; RU 'коммит'.
examples:
  - "Commit my changes"
---

# Commit

Skill body text here.
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# ── render_agent_toml ──────────────────────────────────────────────


def test_agent_toml_is_valid_with_all_keys(tmp_path: Path) -> None:
    path = _write(tmp_path, "a.md", _AGENT_MD)
    out = render_agent_toml(path)
    _, _, toml_part = out.partition("\n# source-sha256: ")
    body = toml_part.split("\n", 1)[1]
    table = tomllib.loads(body)
    assert table["name"] == "example-agent"
    assert table["description"] == "An example agent demonstrating frontmatter"
    assert table["model"] == "opus"
    assert "developer_instructions" in table
    assert table["developer_instructions"].startswith("# Example Agent")
    assert "You are a specialized agent" in table["developer_instructions"]


def test_agent_toml_omits_model_when_absent(tmp_path: Path) -> None:
    path = _write(tmp_path, "a.md", _AGENT_NO_MODEL)
    out = render_agent_toml(path)
    table = tomllib.loads(out)
    assert "model" not in table
    assert table["name"] == "plain-agent"


def test_agent_toml_carries_header(tmp_path: Path) -> None:
    path = _write(tmp_path, "a.md", _AGENT_MD)
    out = render_agent_toml(path)
    lines = out.splitlines()
    assert lines[0] == "# managed-by: ai-dotfiles"
    assert lines[1].startswith("# source-sha256: ")
    expected = hashlib.sha256(_AGENT_MD.encode("utf-8")).hexdigest()
    assert lines[1] == f"# source-sha256: {expected}"


def test_agent_toml_rejects_missing_name(tmp_path: Path) -> None:
    path = _write(tmp_path, "a.md", "---\ndescription: x\n---\nbody\n")
    with pytest.raises(ElementError, match="name"):
        render_agent_toml(path)


def test_agent_toml_rejects_missing_description(tmp_path: Path) -> None:
    path = _write(tmp_path, "a.md", "---\nname: x\n---\nbody\n")
    with pytest.raises(ElementError, match="description"):
        render_agent_toml(path)


def test_agent_toml_escapes_quotes_and_backticks(tmp_path: Path) -> None:
    md = (
        "---\nname: tricky\ndescription: An agent\n---\n\n"
        'Body with "double quotes" and `backticks`.\n'
        "Second line with a backslash \\ and 'singles'.\n"
    )
    path = _write(tmp_path, "a.md", md)
    out = render_agent_toml(path)
    # tomllib round-trips: escaping is correct iff this parses and the
    # body comes back byte-identical to the source body.
    table = tomllib.loads(out)
    instructions = table["developer_instructions"]
    assert '"double quotes"' in instructions
    assert "`backticks`" in instructions
    assert "\\" in instructions
    assert "'singles'" in instructions


def test_agent_toml_handles_multiline_body(tmp_path: Path) -> None:
    md = "---\nname: m\ndescription: d\n---\n\nline1\nline2\n\nline4\n"
    path = _write(tmp_path, "a.md", md)
    table = tomllib.loads(render_agent_toml(path))
    assert table["developer_instructions"] == "line1\nline2\n\nline4"


# ── render_skill_md ────────────────────────────────────────────────


def test_skill_md_trims_description_to_first_sentence(tmp_path: Path) -> None:
    path = _write(tmp_path, "SKILL.md", _SKILL_MD)
    out = render_skill_md(path)
    assert 'description: "Write a Conventional Commit."' in out
    assert "Trigger on EN" not in out


def test_skill_md_preserves_body_and_other_frontmatter(tmp_path: Path) -> None:
    path = _write(tmp_path, "SKILL.md", _SKILL_MD)
    out = render_skill_md(path)
    assert "name: commit" in out
    assert "examples:" in out
    assert '  - "Commit my changes"' in out
    assert "# Commit\n\nSkill body text here." in out


def test_skill_md_carries_header(tmp_path: Path) -> None:
    path = _write(tmp_path, "SKILL.md", _SKILL_MD)
    out = render_skill_md(path)
    lines = out.splitlines()
    assert lines[0] == "# managed-by: ai-dotfiles"
    expected = hashlib.sha256(_SKILL_MD.encode("utf-8")).hexdigest()
    assert lines[1] == f"# source-sha256: {expected}"
    assert lines[2] == "---"


def test_skill_md_description_without_terminator_is_kept(tmp_path: Path) -> None:
    md = "---\nname: s\ndescription: A description with no period\n---\n\nbody\n"
    path = _write(tmp_path, "SKILL.md", md)
    out = render_skill_md(path)
    assert 'description: "A description with no period"' in out


def test_skill_md_rejects_missing_frontmatter(tmp_path: Path) -> None:
    path = _write(tmp_path, "SKILL.md", "# No frontmatter\n\nbody\n")
    with pytest.raises(ElementError, match="frontmatter"):
        render_skill_md(path)


def test_skill_md_rejects_missing_description(tmp_path: Path) -> None:
    path = _write(tmp_path, "SKILL.md", "---\nname: s\n---\n\nbody\n")
    with pytest.raises(ElementError, match="description"):
        render_skill_md(path)


# ── header / hash stability ────────────────────────────────────────


def test_hash_is_stable_for_unchanged_input(tmp_path: Path) -> None:
    path = _write(tmp_path, "a.md", _AGENT_MD)
    first = render_agent_toml(path)
    second = render_agent_toml(path)
    assert first == second


def test_hash_changes_when_source_changes(tmp_path: Path) -> None:
    path = _write(tmp_path, "a.md", _AGENT_MD)
    before = render_agent_toml(path).splitlines()[1]
    path.write_text(_AGENT_MD + "\nextra line\n", encoding="utf-8")
    after = render_agent_toml(path).splitlines()[1]
    assert before != after


def test_hash_is_of_source_not_output(tmp_path: Path) -> None:
    path = _write(tmp_path, "a.md", _AGENT_MD)
    out = render_agent_toml(path)
    sha_line = out.splitlines()[1]
    expected = hashlib.sha256(_AGENT_MD.encode("utf-8")).hexdigest()
    assert sha_line == f"# source-sha256: {expected}"

"""Unit tests for ai_dotfiles.core.codex_install."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ai_dotfiles.core.codex_install import (
    MANAGED_BY_HEADER,
    SKILL_META_FILENAME,
    install_codex_agent,
    install_codex_rule_skill,
    install_codex_skill,
    is_managed,
    is_managed_skill,
    is_stale,
    remove_codex_agent,
    remove_codex_skill,
)
from ai_dotfiles.core.errors import ElementError
from ai_dotfiles.core.frontmatter import parse_frontmatter

_AGENT_MD = """\
---
name: example-agent
description: An example agent.
model: opus
---

# Example Agent

Body text.
"""

_SKILL_MD = """\
---
name: commit
description: Write a Conventional Commit. Trigger phrase here.
---

# Commit

Skill body.
"""


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ── install_codex_agent ────────────────────────────────────────────


def test_install_agent_writes_managed_toml(tmp_path: Path) -> None:
    source = _write(tmp_path / "catalog" / "a.md", _AGENT_MD)
    target = tmp_path / ".codex" / "agents" / "example-agent.toml"

    status = install_codex_agent(source, target)

    assert status == "created"
    assert target.is_file()
    assert not target.is_symlink()
    lines = target.read_text(encoding="utf-8").splitlines()
    assert lines[0] == MANAGED_BY_HEADER
    assert lines[1].startswith("# source-sha256: ")


def test_install_agent_reports_updated_on_second_write(tmp_path: Path) -> None:
    source = _write(tmp_path / "a.md", _AGENT_MD)
    target = tmp_path / "out" / "a.toml"

    assert install_codex_agent(source, target) == "created"
    assert install_codex_agent(source, target) == "updated"


def test_install_agent_propagates_render_error(tmp_path: Path) -> None:
    source = _write(tmp_path / "a.md", "---\nname: x\n---\nbody\n")
    with pytest.raises(ElementError, match="description"):
        install_codex_agent(source, tmp_path / "a.toml")


# ── install_codex_skill ────────────────────────────────────────────


def test_install_skill_generates_skill_md_and_symlinks_support(
    tmp_path: Path,
) -> None:
    skill_src = tmp_path / "catalog" / "skills" / "commit"
    _write(skill_src / "SKILL.md", _SKILL_MD)
    _write(skill_src / "scripts" / "run.sh", "echo hi\n")
    _write(skill_src / "references" / "notes.md", "notes\n")

    target = tmp_path / ".agents" / "skills" / "commit"
    status = install_codex_skill(skill_src, target, tmp_path / "backup")

    assert status == "created"
    # The directory is real, SKILL.md is a generated file (not a symlink).
    assert target.is_dir() and not target.is_symlink()
    skill_md = target / "SKILL.md"
    assert skill_md.is_file() and not skill_md.is_symlink()
    # ai-19: SKILL.md starts with '---' on line 1 (no '#' drift header),
    # so Codex's frontmatter parser recognises it.
    text = skill_md.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "---"
    assert "# managed-by" not in text
    front = parse_frontmatter(text)
    assert front["name"] == "commit"
    # Description trimmed to the first sentence (ADR ai-1-4).
    assert front["description"] == "Write a Conventional Commit."
    # The drift/ownership marker lives in a sidecar next to SKILL.md.
    meta = json.loads((target / SKILL_META_FILENAME).read_text(encoding="utf-8"))
    assert meta["managed_by"] == "ai-dotfiles"
    assert (
        meta["source_sha256"]
        == hashlib.sha256(
            (skill_src / "SKILL.md").read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
    )
    # Support files/dirs are symlinks back into the catalog.
    assert (target / "scripts").is_symlink()
    assert (target / "references").is_symlink()
    assert (target / "scripts").resolve() == (skill_src / "scripts").resolve()


def test_install_skill_reports_updated_on_second_install(tmp_path: Path) -> None:
    skill_src = tmp_path / "skills" / "commit"
    _write(skill_src / "SKILL.md", _SKILL_MD)
    target = tmp_path / "out" / "commit"

    assert install_codex_skill(skill_src, target, tmp_path / "b") == "created"
    assert install_codex_skill(skill_src, target, tmp_path / "b") == "updated"


def test_reinstall_overwrites_legacy_broken_skill_md(tmp_path: Path) -> None:
    """Re-rendering replaces an old '#'-header SKILL.md cleanly (ai-19)."""
    skill_src = tmp_path / "skills" / "commit"
    _write(skill_src / "SKILL.md", _SKILL_MD)
    target = tmp_path / "out" / "commit"
    target.mkdir(parents=True)
    # Simulate a Phase-1 generated file with the broken leading '#' header.
    (target / "SKILL.md").write_text(
        f"{MANAGED_BY_HEADER}\n# source-sha256: stale\n---\nname: commit\n---\n",
        encoding="utf-8",
    )

    install_codex_skill(skill_src, target, tmp_path / "b")

    text = (target / "SKILL.md").read_text(encoding="utf-8")
    assert text.splitlines()[0] == "---"
    assert "# managed-by" not in text


# ── install_codex_rule_skill ───────────────────────────────────────


def test_install_rule_skill_writes_frontmatter_and_sidecar(tmp_path: Path) -> None:
    """A synthetic rule-<name> skill starts with '---' and gets a sidecar."""
    rule_md = _write(
        tmp_path / "rules" / "principles.md",
        "# Principles\n\nKeep changes surgical.\n",
    )
    target = tmp_path / ".agents" / "skills" / "rule-principles"

    assert install_codex_rule_skill(rule_md, target) == "created"

    text = (target / "SKILL.md").read_text(encoding="utf-8")
    assert text.splitlines()[0] == "---"
    front = parse_frontmatter(text)
    assert front["name"] == "rule-principles"
    assert is_managed_skill(target) is True


# ── is_managed_skill ───────────────────────────────────────────────


def test_is_managed_skill_true_for_generated_skill(tmp_path: Path) -> None:
    skill_src = tmp_path / "skills" / "commit"
    _write(skill_src / "SKILL.md", _SKILL_MD)
    target = tmp_path / "out" / "commit"
    install_codex_skill(skill_src, target, tmp_path / "b")
    assert is_managed_skill(target) is True


def test_is_managed_skill_false_for_user_authored_skill(tmp_path: Path) -> None:
    """A skill dir with no .ai-dotfiles-meta sidecar is user-authored."""
    user_skill = tmp_path / ".agents" / "skills" / "mine"
    _write(user_skill / "SKILL.md", "---\nname: mine\n---\n\nbody\n")
    assert is_managed_skill(user_skill) is False


def test_is_managed_skill_false_for_missing_directory(tmp_path: Path) -> None:
    assert is_managed_skill(tmp_path / "absent") is False


# ── is_managed ─────────────────────────────────────────────────────


def test_is_managed_true_for_generated_file(tmp_path: Path) -> None:
    source = _write(tmp_path / "a.md", _AGENT_MD)
    target = tmp_path / "a.toml"
    install_codex_agent(source, target)
    assert is_managed(target) is True


def test_is_managed_false_for_user_authored_file(tmp_path: Path) -> None:
    user_file = _write(tmp_path / "user.toml", 'name = "mine"\n')
    assert is_managed(user_file) is False


def test_is_managed_false_for_missing_file(tmp_path: Path) -> None:
    assert is_managed(tmp_path / "nope.toml") is False


# ── is_stale ───────────────────────────────────────────────────────


def test_is_stale_false_when_source_unchanged(tmp_path: Path) -> None:
    source = _write(tmp_path / "a.md", _AGENT_MD)
    target = tmp_path / "a.toml"
    install_codex_agent(source, target)
    assert is_stale(target, source) is False


def test_is_stale_true_when_source_changed(tmp_path: Path) -> None:
    source = _write(tmp_path / "a.md", _AGENT_MD)
    target = tmp_path / "a.toml"
    install_codex_agent(source, target)

    source.write_text(_AGENT_MD + "\nan extra line\n", encoding="utf-8")
    assert is_stale(target, source) is True


def test_is_stale_true_for_missing_generated_file(tmp_path: Path) -> None:
    source = _write(tmp_path / "a.md", _AGENT_MD)
    assert is_stale(tmp_path / "absent.toml", source) is True


def test_is_stale_true_when_header_absent(tmp_path: Path) -> None:
    source = _write(tmp_path / "a.md", _AGENT_MD)
    no_header = _write(tmp_path / "x.toml", 'name = "x"\n')
    assert is_stale(no_header, source) is True


def test_is_stale_recognizes_skill_md_drift(tmp_path: Path) -> None:
    skill_src = tmp_path / "skills" / "commit"
    _write(skill_src / "SKILL.md", _SKILL_MD)
    target = tmp_path / "out" / "commit"
    install_codex_skill(skill_src, target, tmp_path / "b")

    generated = target / "SKILL.md"
    source = skill_src / "SKILL.md"
    assert is_stale(generated, source) is False

    source.write_text(_SKILL_MD + "\nmore\n", encoding="utf-8")
    assert is_stale(generated, source) is True


def test_is_stale_matches_render_layer_hash(tmp_path: Path) -> None:
    """The recorded hash is of the SOURCE content, not the rendered output."""
    source = _write(tmp_path / "a.md", _AGENT_MD)
    target = tmp_path / "a.toml"
    install_codex_agent(source, target)

    recorded = target.read_text(encoding="utf-8").splitlines()[1]
    expected = hashlib.sha256(_AGENT_MD.encode("utf-8")).hexdigest()
    assert recorded == f"# source-sha256: {expected}"


# ── remove_codex_agent / remove_codex_skill ────────────────────────


def test_remove_agent_deletes_managed_file(tmp_path: Path) -> None:
    source = _write(tmp_path / "a.md", _AGENT_MD)
    target = tmp_path / "a.toml"
    install_codex_agent(source, target)

    assert remove_codex_agent(target) is True
    assert not target.exists()


def test_remove_agent_leaves_user_authored_file(tmp_path: Path) -> None:
    user_file = _write(tmp_path / "user.toml", 'name = "mine"\n')
    assert remove_codex_agent(user_file) is False
    assert user_file.exists()


def test_remove_agent_noop_for_missing_file(tmp_path: Path) -> None:
    assert remove_codex_agent(tmp_path / "absent.toml") is False


def test_remove_skill_deletes_managed_directory(tmp_path: Path) -> None:
    skill_src = tmp_path / "skills" / "commit"
    _write(skill_src / "SKILL.md", _SKILL_MD)
    _write(skill_src / "scripts" / "run.sh", "echo\n")
    target = tmp_path / "out" / "commit"
    install_codex_skill(skill_src, target, tmp_path / "b")

    assert remove_codex_skill(target) is True
    assert not target.exists()
    # Catalog source is untouched — only the symlink was dropped.
    assert (skill_src / "scripts" / "run.sh").is_file()


def test_remove_skill_leaves_user_authored_directory(tmp_path: Path) -> None:
    user_skill = tmp_path / ".agents" / "skills" / "mine"
    _write(user_skill / "SKILL.md", "---\nname: mine\n---\n\nbody\n")
    assert remove_codex_skill(user_skill) is False
    assert (user_skill / "SKILL.md").exists()


def test_remove_skill_noop_for_missing_directory(tmp_path: Path) -> None:
    assert remove_codex_skill(tmp_path / "absent") is False

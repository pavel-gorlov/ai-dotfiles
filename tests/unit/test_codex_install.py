"""Unit tests for ai_dotfiles.core.codex_install."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from pathlib import Path

import pytest

from ai_dotfiles.core.codex_install import (
    MANAGED_BY_HEADER,
    SKILL_DESCRIPTION_MAX,
    SKILL_META_FILENAME,
    install_codex_agent,
    install_codex_rule_skill,
    install_codex_skill,
    is_managed,
    is_managed_skill,
    is_stale,
    remove_codex_agent,
    remove_codex_skill,
    remove_codex_skill_link,
    skill_symlink_ok,
    symlink_codex_skill,
)
from ai_dotfiles.core.codex_render import source_sha256
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


def test_install_skill_generates_skill_md_and_copies_support(
    tmp_path: Path,
) -> None:
    skill_src = tmp_path / "catalog" / "skills" / "commit"
    _write(skill_src / "SKILL.md", _SKILL_MD)
    _write(skill_src / "scripts" / "run.sh", "echo hi\n")
    _write(skill_src / "references" / "notes.md", "notes\n")

    target = tmp_path / ".agents" / "skills" / "commit"
    status = install_codex_skill(skill_src, target)

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
    # ai-20: support files/dirs are real copies, not symlinks into the
    # catalog — the Codex target is self-contained.
    assert (target / "scripts").is_dir() and not (target / "scripts").is_symlink()
    assert (target / "references").is_dir() and not (target / "references").is_symlink()
    assert not (target / "scripts" / "run.sh").is_symlink()
    assert (target / "scripts" / "run.sh").read_text() == "echo hi\n"
    assert (target / "references" / "notes.md").read_text() == "notes\n"


def test_install_skill_leaves_no_symlinks_under_target(tmp_path: Path) -> None:
    """No symlink anywhere under the installed Codex skill directory (ai-20)."""
    skill_src = tmp_path / "catalog" / "skills" / "commit"
    _write(skill_src / "SKILL.md", _SKILL_MD)
    _write(skill_src / "scripts" / "run.sh", "echo hi\n")
    _write(skill_src / "references" / "notes.md", "notes\n")
    _write(skill_src / "assets" / "logo.txt", "logo\n")

    target = tmp_path / ".agents" / "skills" / "commit"
    install_codex_skill(skill_src, target)

    symlinks = [p for p in target.rglob("*") if p.is_symlink()]
    assert symlinks == []


def test_install_skill_preserves_executable_bit_on_scripts(tmp_path: Path) -> None:
    """Executable bits on copied scripts/* survive the copy (ai-20)."""
    skill_src = tmp_path / "catalog" / "skills" / "commit"
    _write(skill_src / "SKILL.md", _SKILL_MD)
    script = _write(skill_src / "scripts" / "run.sh", "echo hi\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    target = tmp_path / ".agents" / "skills" / "commit"
    install_codex_skill(skill_src, target)

    copied = target / "scripts" / "run.sh"
    assert os.access(copied, os.X_OK)
    assert copied.stat().st_mode & stat.S_IXUSR


def test_reinstall_refreshes_copied_support_files(tmp_path: Path) -> None:
    """Re-install drops a support file the catalog has since removed (ai-20)."""
    skill_src = tmp_path / "catalog" / "skills" / "commit"
    _write(skill_src / "SKILL.md", _SKILL_MD)
    _write(skill_src / "scripts" / "run.sh", "echo hi\n")
    stale = _write(skill_src / "references" / "old.md", "old\n")

    target = tmp_path / ".agents" / "skills" / "commit"
    install_codex_skill(skill_src, target)
    assert (target / "references" / "old.md").is_file()

    # The catalog renames a file and drops a whole support dir.
    stale.unlink()
    _write(skill_src / "references" / "new.md", "new\n")
    shutil.rmtree(skill_src / "scripts")

    install_codex_skill(skill_src, target)

    assert (target / "references" / "new.md").read_text() == "new\n"
    assert not (target / "references" / "old.md").exists()
    assert not (target / "scripts").exists()


def test_install_skill_reports_updated_on_second_install(tmp_path: Path) -> None:
    skill_src = tmp_path / "skills" / "commit"
    _write(skill_src / "SKILL.md", _SKILL_MD)
    target = tmp_path / "out" / "commit"

    assert install_codex_skill(skill_src, target) == "created"
    assert install_codex_skill(skill_src, target) == "updated"


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

    install_codex_skill(skill_src, target)

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
    install_codex_skill(skill_src, target)
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


def test_is_stale_true_for_artefact_from_an_older_generator(tmp_path: Path) -> None:
    """A renderer change must reach projects whose sources never moved.

    This is the migration path for every ``.toml`` generated before the
    ``model`` pin was dropped: the source SHA still matches, so without
    the generator check `status` would call these files fresh forever and
    the stale pin would never be rewritten.
    """
    source = _write(tmp_path / "a.md", _AGENT_MD)
    target = tmp_path / "a.toml"
    install_codex_agent(source, target)
    assert is_stale(target, source) is False

    lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
    assert lines[2].startswith("# generator: ")
    lines[2] = "# generator: 1\n"
    target.write_text("".join(lines), encoding="utf-8")

    assert is_stale(target, source) is True


def test_is_stale_true_for_pre_generator_header(tmp_path: Path) -> None:
    """The two-line header shipped in 0.2.0 and earlier — no version line."""
    source = _write(tmp_path / "a.md", _AGENT_MD)
    legacy = _write(
        tmp_path / "legacy.toml",
        f"# managed-by: ai-dotfiles\n"
        f"# source-sha256: {source_sha256(_AGENT_MD)}\n"
        f'name = "example-agent"\n',
    )
    assert is_stale(legacy, source) is True


def test_is_stale_recognizes_skill_md_drift(tmp_path: Path) -> None:
    skill_src = tmp_path / "skills" / "commit"
    _write(skill_src / "SKILL.md", _SKILL_MD)
    target = tmp_path / "out" / "commit"
    install_codex_skill(skill_src, target)

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
    install_codex_skill(skill_src, target)

    assert remove_codex_skill(target) is True
    assert not target.exists()
    # Removing the dir drops the copied support files with it (ai-20);
    # the catalog source is a separate tree and stays untouched.
    assert (skill_src / "scripts" / "run.sh").is_file()


def test_remove_skill_leaves_user_authored_directory(tmp_path: Path) -> None:
    user_skill = tmp_path / ".agents" / "skills" / "mine"
    _write(user_skill / "SKILL.md", "---\nname: mine\n---\n\nbody\n")
    assert remove_codex_skill(user_skill) is False
    assert (user_skill / "SKILL.md").exists()


def test_remove_skill_noop_for_missing_directory(tmp_path: Path) -> None:
    assert remove_codex_skill(tmp_path / "absent") is False


# ── gated symlink helpers (shared by migrate + the global scope) ──────────


def _raw_skill(tmp_path: Path, name: str, description: str = "Short.") -> Path:
    skill = tmp_path / "src-skills" / name
    _write(
        skill / "SKILL.md",
        f"---\nname: {name}\ndescription: {description}\n---\n\nbody\n",
    )
    return skill


def test_skill_symlink_ok_within_limits(tmp_path: Path) -> None:
    skill = _raw_skill(tmp_path, "commit")
    ok, reason = skill_symlink_ok(skill, "commit")
    assert ok is True
    assert "symlink" in reason


def test_skill_symlink_ok_rejects_over_cap_description(tmp_path: Path) -> None:
    skill = _raw_skill(
        tmp_path, "verbose", description="x" * (SKILL_DESCRIPTION_MAX + 1)
    )
    ok, reason = skill_symlink_ok(skill, "verbose")
    assert ok is False
    assert "cap" in reason


def test_skill_symlink_ok_rejects_bad_name(tmp_path: Path) -> None:
    skill = _raw_skill(tmp_path, "BadName")
    ok, reason = skill_symlink_ok(skill, "BadName")
    assert ok is False
    assert "hyphen-case" in reason


def test_symlink_codex_skill_relative_and_absolute(tmp_path: Path) -> None:
    skill = _raw_skill(tmp_path, "commit")
    rel_target = tmp_path / "proj" / ".agents" / "skills" / "commit"
    abs_target = tmp_path / "codex" / "skills" / "commit"

    assert symlink_codex_skill(skill, rel_target) == "linked"
    assert symlink_codex_skill(skill, rel_target) == "already-linked"
    assert not os.path.isabs(os.readlink(rel_target))

    assert symlink_codex_skill(skill, abs_target, relative=False) == "linked"
    assert os.path.isabs(os.readlink(abs_target))
    assert abs_target.resolve() == skill.resolve()


def test_symlink_codex_skill_replaces_managed_render(tmp_path: Path) -> None:
    skill = _raw_skill(tmp_path, "commit")
    target = tmp_path / "codex" / "skills" / "commit"
    install_codex_skill(skill, target)
    assert target.is_dir() and not target.is_symlink()

    assert symlink_codex_skill(skill, target, relative=False) == "linked"
    assert target.is_symlink()


def test_symlink_codex_skill_refuses_user_authored_dir(tmp_path: Path) -> None:
    skill = _raw_skill(tmp_path, "commit")
    target = tmp_path / "codex" / "skills" / "commit"
    _write(target / "SKILL.md", "---\nname: commit\n---\n\nuser body\n")
    from ai_dotfiles.core.errors import LinkError

    with pytest.raises(LinkError, match="user-authored"):
        symlink_codex_skill(skill, target, relative=False)


def test_install_codex_skill_replaces_symlink_without_writing_source(
    tmp_path: Path,
) -> None:
    """Rendering over a symlink must not write through it into the source."""
    skill = _raw_skill(tmp_path, "commit")
    target = tmp_path / "codex" / "skills" / "commit"
    symlink_codex_skill(skill, target, relative=False)

    install_codex_skill(skill, target)

    assert target.is_dir() and not target.is_symlink()
    # The source stayed a raw skill — no sidecar leaked into it.
    assert not (skill / SKILL_META_FILENAME).exists()
    assert (target / SKILL_META_FILENAME).is_file()


def test_remove_codex_skill_link_only_removes_links_into_root(tmp_path: Path) -> None:
    catalog_root = tmp_path / "catalog"
    ours = _raw_skill(catalog_root, "commit")
    foreign = _raw_skill(tmp_path / "elsewhere", "other")
    skills = tmp_path / "codex" / "skills"
    symlink_codex_skill(ours, skills / "commit", relative=False)
    symlink_codex_skill(foreign, skills / "other", relative=False)

    assert remove_codex_skill_link(skills / "commit", catalog_root) is True
    assert not (skills / "commit").exists()
    # A user symlink pointing elsewhere is never touched.
    assert remove_codex_skill_link(skills / "other", catalog_root) is False
    assert (skills / "other").is_symlink()
    # A non-symlink and a missing path are no-ops.
    assert remove_codex_skill_link(skills / "missing", catalog_root) is False


def test_remove_codex_skill_link_removes_dangling_catalog_link(tmp_path: Path) -> None:
    catalog_root = tmp_path / "catalog"
    ours = _raw_skill(catalog_root, "gone")
    skills = tmp_path / "codex" / "skills"
    symlink_codex_skill(ours, skills / "gone", relative=False)
    shutil.rmtree(ours)

    assert remove_codex_skill_link(skills / "gone", catalog_root) is True
    assert not (skills / "gone").is_symlink()

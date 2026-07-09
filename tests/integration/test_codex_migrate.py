"""Migrate LOCAL project elements to the Codex target (``ai-dotfiles migrate``)."""

import os
from pathlib import Path

import pytest
import tomllib

from ai_dotfiles.core import codex_migrate, paths
from ai_dotfiles.core.codex_local_registry import load_local_registry

pytestmark = pytest.mark.integration


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_project(root: Path) -> None:
    claude = root / ".claude"
    _write(
        claude / "skills" / "local-skill" / "SKILL.md",
        "---\nname: local-skill\ndescription: A short local skill.\n---\nBody.\n",
    )
    _write(
        claude / "skills" / "big-skill" / "SKILL.md",
        f"---\nname: big-skill\ndescription: {'x' * 1100}\n---\nBody.\n",
    )
    _write(
        claude / "agents" / "local-agent.md",
        "---\nname: local-agent\ndescription: A local agent.\n---\nInstructions.\n",
    )
    _write(claude / "rules" / "local-rule.md", "# Local rule\n\nAlways do the thing.\n")
    _write(root / "CLAUDE.md", "# Project\n\nCanonical instructions live here.\n")
    _write(claude / "workflows" / "recipe.js", "// bespoke workflow\n")


def test_migrate_applies_symlink_render_and_fallback(
    tmp_path: Path, tmp_storage: Path
) -> None:
    root = tmp_path / "proj"
    _build_project(root)

    report = codex_migrate.migrate_to_codex(root, manifest_packages=[])

    strategy = {a.name: a.strategy for a in report.actions}
    # Normal skill -> auto-fresh relative symlink.
    assert strategy["local-skill"] == "symlink"
    link = paths.project_codex_skills_dir(root) / "local-skill"
    assert link.is_symlink()
    assert os.readlink(link) == "../../.claude/skills/local-skill"
    # Over-cap skill -> rendered (real dir with trimmed SKILL.md + sidecar).
    assert strategy["big-skill"] == "render-skill"
    big = paths.project_codex_skills_dir(root) / "big-skill"
    assert big.is_dir() and not big.is_symlink()
    assert (big / "SKILL.md").is_file()
    assert (big / ".ai-dotfiles-meta").is_file()
    # Agent -> rendered TOML.
    assert strategy["local-agent"] == "render-agent"
    assert (paths.project_codex_agents_dir(root) / "local-agent.toml").is_file()
    # Description-only rule -> synthetic rule-<name> skill.
    assert strategy["local-rule"] == "rule-skill"
    assert (
        paths.project_codex_skills_dir(root) / "rule-local-rule" / "SKILL.md"
    ).is_file()

    # CLAUDE.md wired as a Codex project-doc fallback.
    assert report.fallback_changed is True
    config = tomllib.loads(
        (root / ".codex" / "config.toml").read_text(encoding="utf-8")
    )
    assert config["project_doc_fallback_filenames"] == ["CLAUDE.md"]

    # Workflows reported as Claude-only.
    assert any("workflows/recipe.js" in label for label, _ in report.claude_only)


def test_migrate_records_local_provenance(tmp_path: Path, tmp_storage: Path) -> None:
    root = tmp_path / "proj"
    _build_project(root)

    codex_migrate.migrate_to_codex(root, manifest_packages=[])

    registry = load_local_registry(root)
    assert registry["skills"]["local-skill"] == "symlink"
    assert registry["skills"]["big-skill"] == "render"
    assert registry["skills"]["rule-local-rule"] == "render"
    assert registry["agents"]["local-agent"] == "render"


def test_migrate_dry_run_writes_nothing(tmp_path: Path, tmp_storage: Path) -> None:
    root = tmp_path / "proj"
    _build_project(root)

    report = codex_migrate.migrate_to_codex(root, manifest_packages=[], dry_run=True)

    assert report.dry_run is True
    assert report.actions  # planned actions present
    assert report.fallback_changed is True  # would set it
    # Nothing on disk.
    assert not (root / ".agents").exists()
    assert not (root / ".codex").exists()


def test_migrate_is_idempotent(tmp_path: Path, tmp_storage: Path) -> None:
    root = tmp_path / "proj"
    _build_project(root)

    codex_migrate.migrate_to_codex(root, manifest_packages=[])
    # Second run must not raise and must keep the symlink a symlink.
    codex_migrate.migrate_to_codex(root, manifest_packages=[])

    link = paths.project_codex_skills_dir(root) / "local-skill"
    assert link.is_symlink()


def test_migrate_excludes_manifest_named_elements(
    tmp_path: Path, tmp_storage: Path
) -> None:
    root = tmp_path / "proj"
    _build_project(root)

    report = codex_migrate.migrate_to_codex(
        root, manifest_packages=["skill:local-skill"]
    )

    names = {a.name for a in report.actions}
    assert "local-skill" not in names  # manifest-declared -> not a local element
    assert "local-agent" in names


def test_prune_protects_migrated_artefacts(tmp_path: Path, tmp_storage: Path) -> None:
    from ai_dotfiles.commands.install import _codex_local_protected

    root = tmp_path / "proj"
    _build_project(root)
    codex_migrate.migrate_to_codex(root, manifest_packages=[])

    keep_skills, keep_agents, _ = _codex_local_protected(root)
    assert paths.project_codex_skills_dir(root) / "big-skill" in keep_skills
    assert paths.project_codex_skills_dir(root) / "rule-local-rule" in keep_skills
    assert paths.project_codex_agents_dir(root) / "local-agent.toml" in keep_agents


def test_migrate_carries_only_user_authored_mcp(
    tmp_path: Path, tmp_storage: Path
) -> None:
    root = tmp_path / "proj"
    _build_project(root)
    # A user-authored server (storybook) and a domain-owned one (playwright).
    _write(
        root / ".mcp.json",
        '{"mcpServers": {'
        '"storybook": {"type": "http", "url": "http://localhost:6006/mcp"}, '
        '"playwright": {"command": "npx", "args": ["@playwright/mcp"]}}}',
    )
    _write(
        root / ".claude" / ".ai-dotfiles-mcp-ownership.json",
        '{"playwright": ["playwright-e2e"]}',
    )

    report = codex_migrate.migrate_to_codex(root, manifest_packages=[])

    assert "storybook" in report.mcp_added
    assert "playwright" not in report.mcp_added  # domain-owned, not user
    config = tomllib.loads(
        (root / ".codex" / "config.toml").read_text(encoding="utf-8")
    )
    assert "storybook" in config["mcp_servers"]
    assert "playwright" not in config.get("mcp_servers", {})

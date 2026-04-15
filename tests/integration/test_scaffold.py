"""Integration tests for scaffold generator."""

from __future__ import annotations

import json
import os
from importlib import resources
from pathlib import Path

import pytest

from ai_dotfiles.scaffold.generator import (
    generate_element_from_template,
    generate_project_manifest,
    generate_storage_scaffold,
)

pytestmark = pytest.mark.integration


EXPECTED_FILES = [
    "global/README.md",
    "global/CLAUDE.md",
    "global/settings.json",
    "global/hooks/README.md",
    "global/hooks/post-edit-lint.sh",
    "global/hooks/pre-commit-check.sh",
    "global/output-styles/README.md",
    "global/output-styles/concise-ru.md",
    "global.json",
    "catalog/README.md",
    "catalog/_example/skills/example-skill/SKILL.md",
    "catalog/_example/agents/example-agent.md",
    "catalog/_example/rules/example-style.md",
    "catalog/_example/hooks/example-lint.sh",
    "catalog/_example/settings.fragment.json",
    "stacks/README.md",
    "stacks/_example.conf",
    "README.md",
    ".gitignore",
]

EXPECTED_EMPTY_DIRS = [
    "catalog/skills",
    "catalog/agents",
    "catalog/rules",
]


def test_generate_storage_scaffold(tmp_path: Path) -> None:
    root = tmp_path / ".ai-dotfiles"
    generate_storage_scaffold(root)

    for rel in EXPECTED_FILES:
        assert (root / rel).is_file(), f"Missing file: {rel}"

    for rel in EXPECTED_EMPTY_DIRS:
        assert (root / rel).is_dir(), f"Missing dir: {rel}"


def test_generate_storage_scaffold_files_not_empty(tmp_path: Path) -> None:
    root = tmp_path / ".ai-dotfiles"
    generate_storage_scaffold(root)

    for rel in EXPECTED_FILES:
        content = (root / rel).read_text(encoding="utf-8")
        assert content.strip(), f"Empty content: {rel}"

    settings = json.loads((root / "global/settings.json").read_text())
    assert "permissions" in settings

    manifest = json.loads((root / "global.json").read_text())
    assert manifest == {"packages": []}


def test_generate_storage_scaffold_sh_executable(tmp_path: Path) -> None:
    root = tmp_path / ".ai-dotfiles"
    generate_storage_scaffold(root)

    sh_files = [
        root / "global/hooks/post-edit-lint.sh",
        root / "global/hooks/pre-commit-check.sh",
        root / "catalog/_example/hooks/example-lint.sh",
    ]
    for sh in sh_files:
        mode = sh.stat().st_mode
        assert mode & 0o111, f"Not executable: {sh}"
        # Verify shebang present
        assert sh.read_text().startswith("#!"), f"Missing shebang: {sh}"
        # Also validate os.access when possible (skipped on odd platforms)
        assert os.access(sh, os.X_OK)


def test_generate_project_manifest(tmp_path: Path) -> None:
    generate_project_manifest(tmp_path)

    manifest = tmp_path / "ai-dotfiles.json"
    assert manifest.is_file()
    assert json.loads(manifest.read_text()) == {"packages": []}


def test_generate_project_manifest_no_overwrite(tmp_path: Path) -> None:
    manifest = tmp_path / "ai-dotfiles.json"
    existing = {"packages": ["skill:foo"]}
    manifest.write_text(json.dumps(existing))

    generate_project_manifest(tmp_path)

    assert json.loads(manifest.read_text()) == existing


def test_generate_element_skill(tmp_path: Path) -> None:
    dest = tmp_path / "my-skill"
    result = generate_element_from_template("skill", "my-skill", dest)

    assert result == dest / "SKILL.md"
    assert result.is_file()
    content = result.read_text()
    assert "name: my-skill" in content
    assert "# my-skill" in content
    assert "{{name}}" not in content


def test_generate_element_agent(tmp_path: Path) -> None:
    dest = tmp_path / "my-agent.md"
    result = generate_element_from_template("agent", "my-agent", dest)

    assert result == dest
    assert result.is_file()
    content = result.read_text()
    assert "name: my-agent" in content
    assert "{{name}}" not in content


def test_generate_element_rule(tmp_path: Path) -> None:
    dest = tmp_path / "my-rule.md"
    result = generate_element_from_template("rule", "my-rule", dest)

    assert result == dest
    assert result.is_file()
    content = result.read_text()
    assert "name: my-rule" in content
    assert "{{name}}" not in content


def test_generate_element_unknown_type(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown element_type"):
        generate_element_from_template("widget", "x", tmp_path / "x.md")


def test_templates_loadable() -> None:
    expected_templates = [
        "global_readme.md",
        "global_claude.md",
        "global_settings.json",
        "global_hooks_readme.md",
        "post_edit_lint.sh",
        "pre_commit_check.sh",
        "output_styles_readme.md",
        "concise_ru.md",
        "catalog_readme.md",
        "example_skill.md",
        "example_agent.md",
        "example_rule.md",
        "example_hook.sh",
        "example_settings_fragment.json",
        "stacks_readme.md",
        "example_stack.conf",
        "root_readme.md",
        "gitignore",
        "skill_template.md",
        "agent_template.md",
        "rule_template.md",
    ]
    pkg = resources.files("ai_dotfiles.scaffold.templates")
    for name in expected_templates:
        resource = pkg.joinpath(name)
        assert resource.is_file(), f"Template not loadable: {name}"
        assert resource.read_text(encoding="utf-8").strip()

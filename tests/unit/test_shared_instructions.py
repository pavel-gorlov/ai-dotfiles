"""Shared instruction ownership and byte-preserving managed Markdown."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ai_dotfiles.core.agents_md import (
    block_matches,
    iter_rule_block_names,
    remove_rule_blocks,
    strip_rule_blocks,
    upsert_rule_block,
)
from ai_dotfiles.core.codex_install import remove_codex_rule_blocks, rule_block_state
from ai_dotfiles.core.codex_local_registry import registry_path
from ai_dotfiles.core.dsh_layout import project_layout
from ai_dotfiles.core.elements import parse_elements
from ai_dotfiles.core.errors import ConfigError, ElementError
from ai_dotfiles.core.rule_classify import RuleClass, classify_rule
from ai_dotfiles.core.shared_instructions import project_instruction_plan
from ai_dotfiles.core.targets import Target


def _rule(
    directory: Path,
    name: str,
    frontmatter: str = "always_on: true",
    body: str = "Shared body.",
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / f"{name}.md"
    source.write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")
    return source


def _registry(path: Path, blocks: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rule_blocks": blocks}), encoding="utf-8")


def test_mixed_targets_share_one_block_without_writes(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    source = _rule(catalog / "rules", "base")
    root = tmp_path / "project"
    plan = project_instruction_plan(
        parse_elements(["rule:base"]), [Target.CODEX, Target.DSH], root, catalog
    )

    assert len(plan.blocks) == 1
    assert plan.blocks[0].sources == (source,)
    assert plan.blocks[0].contributors == frozenset({Target.CODEX, Target.DSH})
    assert plan.wanted_blocks == {root / "AGENTS.md": {"base"}}
    assert plan.keep_blocks == plan.wanted_blocks
    assert not root.exists()


@pytest.mark.parametrize("remaining", [Target.CODEX, Target.DSH])
def test_removing_one_target_preserves_surviving_shared_block(
    tmp_path: Path, remaining: Target
) -> None:
    catalog = tmp_path / "catalog"
    _rule(catalog / "rules", "base")
    root = tmp_path / "project"
    elements = parse_elements(["rule:base"])
    initial = project_instruction_plan(
        elements, [Target.CODEX, Target.DSH], root, catalog
    )
    block = initial.blocks[0]
    upsert_rule_block(block.path, block.name, block.body)
    before = block.path.read_bytes()

    remaining_plan = project_instruction_plan(elements, [remaining], root, catalog)
    removable = remaining_plan.removable_names(block.path, ["base", "retired"])
    assert removable == {"retired"}
    assert remove_rule_blocks(block.path, removable) is False
    assert block.path.read_bytes() == before
    empty = project_instruction_plan(elements, [], root, catalog)
    assert empty.removable_names(block.path, ["base"]) == {"base"}
    assert remove_rule_blocks(block.path, {"base"}) is True
    assert not block.path.exists()


@pytest.mark.parametrize("targets", [[], [Target.CODEX], [Target.DSH]])
def test_empty_manifest_protects_both_local_registries(
    tmp_path: Path, targets: list[Target]
) -> None:
    root = tmp_path / "project"
    catalog = tmp_path / "catalog"
    _registry(registry_path(root), {"AGENTS.md": ["codex-local", "shared"]})
    _registry(
        project_layout(root).local_registry_path,
        {"AGENTS.md": ["dsh-local", "shared"], "src/AGENTS.md": ["nested"]},
    )
    before = {
        path: path.read_bytes()
        for path in (registry_path(root), project_layout(root).local_registry_path)
    }

    plan = project_instruction_plan([], targets, root, catalog)
    assert plan.wanted_blocks == {}
    assert plan.protected_blocks == {
        root / "AGENTS.md": {"codex-local", "dsh-local", "shared"},
        root / "src" / "AGENTS.md": {"nested"},
    }
    assert plan.keep_blocks == plan.protected_blocks
    assert plan.removable_names(
        root / "AGENTS.md", ["shared", "dsh-local", "codex-local", "orphan"]
    ) == {"orphan"}
    assert all(path.read_bytes() == content for path, content in before.items())


def test_catalog_and_local_protection_union(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    _rule(catalog / "rules", "catalog-rule")
    root = tmp_path / "project"
    _registry(registry_path(root), {"AGENTS.md": ["local"]})
    plan = project_instruction_plan(
        parse_elements(["rule:catalog-rule"]), [Target.DSH], root, catalog
    )
    assert plan.wanted_blocks == {root / "AGENTS.md": {"catalog-rule"}}
    assert plan.protected_blocks == {root / "AGENTS.md": {"local"}}
    assert plan.keep_blocks == {root / "AGENTS.md": {"catalog-rule", "local"}}
    # Consumers get independent maps and cannot accidentally drop protection.
    keep = plan.keep_blocks
    keep[root / "AGENTS.md"].clear()
    assert plan.keep_blocks == {root / "AGENTS.md": {"catalog-rule", "local"}}


def test_empty_manifest_removes_catalog_block_and_keeps_both_local_bodies(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    agents = root / "AGENTS.md"
    _registry(registry_path(root), {"AGENTS.md": ["codex-local"]})
    _registry(project_layout(root).local_registry_path, {"AGENTS.md": ["dsh-local"]})
    for name, body in (
        ("codex-local", "Local Codex body."),
        ("catalog", "Retired catalog body."),
        ("dsh-local", "Local DSH body."),
    ):
        upsert_rule_block(agents, name, body)
    before = agents.read_bytes()
    plan = project_instruction_plan([], [], root, tmp_path / "catalog")
    names = plan.removable_names(agents, iter_rule_block_names(before.decode()))
    assert names == {"catalog"}
    assert remove_rule_blocks(agents, names) is True
    assert (
        agents.read_bytes() == strip_rule_blocks(before.decode(), {"catalog"}).encode()
    )
    assert block_matches(
        "codex-local", "Local Codex body.", agents.read_bytes().decode()
    )
    assert block_matches("dsh-local", "Local DSH body.", agents.read_bytes().decode())


def test_description_rules_go_only_to_dsh_literal_bridge(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    source = _rule(
        catalog / "rules", "description", "description: Use {{literal}} unchanged"
    )
    root = tmp_path / "project"
    elements = parse_elements(["rule:description"])
    assert classify_rule(source) is RuleClass.DESCRIPTION_ONLY
    mixed = project_instruction_plan(
        elements, [Target.CODEX, Target.DSH], root, catalog
    )
    assert mixed.blocks == ()
    assert mixed.dsh_literal_rules == (source,)
    codex = project_instruction_plan(elements, [Target.CODEX], root, catalog)
    assert codex.blocks == ()
    assert codex.dsh_literal_rules == ()


@pytest.mark.parametrize(
    ("frontmatter", "codex_class", "relative"),
    [
        ('paths: ["src"]\nalways_on: true', RuleClass.PATH_SCOPED, "src/AGENTS.md"),
        ('paths: ["**/*.py"]\nalways_on: true', RuleClass.ALWAYS_ON, "AGENTS.md"),
        ('paths: ["src", "**/*.py"]', RuleClass.DESCRIPTION_ONLY, None),
        ('paths: "src"\nalways_on: true', RuleClass.ALWAYS_ON, "AGENTS.md"),
    ],
)
def test_original_paths_never_add_dsh_activation(
    tmp_path: Path,
    frontmatter: str,
    codex_class: RuleClass,
    relative: str | None,
) -> None:
    catalog = tmp_path / "catalog"
    source = _rule(catalog / "rules", "scoped", frontmatter)
    root = tmp_path / "project"
    elements = parse_elements(["rule:scoped"])
    assert classify_rule(source) is codex_class
    mixed = project_instruction_plan(
        elements, [Target.CODEX, Target.DSH], root, catalog
    )
    assert mixed.dsh_literal_rules == ()
    assert mixed.wanted_blocks == (
        {root / relative: {"scoped"}} if relative is not None else {}
    )
    assert all(
        block.contributors == frozenset({Target.CODEX}) for block in mixed.blocks
    )
    dsh = project_instruction_plan(elements, [Target.DSH], root, catalog)
    assert dsh.blocks == ()
    assert dsh.dsh_literal_rules == ()


def test_empty_source_paths_allow_shared_unconditional_rule(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    _rule(catalog / "rules", "base", "paths: []\nalways_on: true")
    root = tmp_path / "project"
    plan = project_instruction_plan(
        parse_elements(["rule:base"]), [Target.CODEX, Target.DSH], root, catalog
    )
    assert plan.blocks[0].contributors == frozenset({Target.CODEX, Target.DSH})


def test_domain_union_coalesces_identical_sources_and_ignores_metadata(
    tmp_path: Path,
) -> None:
    catalog = tmp_path / "catalog"
    standalone = _rule(catalog / "rules", "same")
    bundled = _rule(catalog / "bundle" / "rules", "same")
    literal = _rule(catalog / "bundle" / "rules", "literal", "description: Literal")
    _rule(catalog / "bundle" / "rules", "README")
    _rule(catalog / "bundle" / "rules", ".hidden")
    _rule(catalog / "bundle" / "agents", "agent", "description: Agent")
    root = tmp_path / "project"
    plan = project_instruction_plan(
        parse_elements(["rule:same", "@bundle", "rule:same"]),
        [Target.CODEX, Target.DSH],
        root,
        catalog,
    )
    assert len(plan.blocks) == 1
    assert plan.blocks[0].sources == (standalone, bundled)
    assert plan.wanted_blocks == {root / "AGENTS.md": {"same"}}
    assert plan.dsh_literal_rules == (literal,)


def test_conflicting_source_bodies_fail_before_writing(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    _rule(catalog / "rules", "same", body="One")
    _rule(catalog / "bundle" / "rules", "same", body="Two")
    root = tmp_path / "project"
    with pytest.raises(ElementError, match="Conflicting shared rule"):
        project_instruction_plan(
            parse_elements(["rule:same", "@bundle"]), [Target.DSH], root, catalog
        )
    assert not root.exists()


def test_source_drift_keeps_compatible_markers_and_replaces_in_place(
    tmp_path: Path,
) -> None:
    catalog = tmp_path / "catalog"
    source = _rule(catalog / "rules", "base", body="Old body.")
    root = tmp_path / "project"
    elements = parse_elements(["rule:base"])
    plan = project_instruction_plan(elements, [Target.CODEX, Target.DSH], root, catalog)
    block = plan.blocks[0]
    upsert_rule_block(block.path, block.name, block.body)
    assert rule_block_state(source, block.path) == "ok"
    old = block.path.read_bytes()
    prefix = b"# User heading  \n\n\n\nUser text.  \n\n"
    suffix = b"\n\n\nUser footer.  \n\n\n"
    block.path.write_bytes(prefix + old + suffix)

    _rule(catalog / "rules", "base", body="New body.")
    assert rule_block_state(source, block.path) == "stale"
    fresh = project_instruction_plan(
        elements, [Target.CODEX, Target.DSH], root, catalog
    )
    new = fresh.blocks[0]
    assert upsert_rule_block(new.path, new.name, new.body) is True
    content = new.path.read_bytes()
    assert content.startswith(prefix)
    assert content.endswith(suffix)
    assert block_matches("base", "New body.", content.decode())
    expected_sha = hashlib.sha256(b"New body.").hexdigest()
    assert f"<!-- ai-dotfiles:rule:base sha256:{expected_sha} -->".encode() in content
    assert iter_rule_block_names(content.decode()) == ["base"]
    assert upsert_rule_block(new.path, new.name, new.body) is False
    assert rule_block_state(source, new.path) == "ok"
    assert remove_codex_rule_blocks(new.path, "base") is True
    assert new.path.read_bytes() == prefix + suffix


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_append_update_remove_preserves_user_bytes(
    tmp_path: Path, newline: bytes
) -> None:
    agents = tmp_path / "AGENTS.md"
    user = b"# User  " + newline * 4 + b"Paragraph.  " + newline * 3
    agents.write_bytes(user)
    upsert_rule_block(agents, "base", "Old body.")
    assert agents.read_bytes().startswith(user)
    suffix = newline * 3 + b"Footer  " + newline * 2
    agents.write_bytes(agents.read_bytes() + suffix)
    upsert_rule_block(agents, "base", "New body.")
    assert agents.read_bytes().startswith(user)
    assert agents.read_bytes().endswith(suffix)
    assert remove_codex_rule_blocks(agents, "base") is True
    assert agents.read_bytes() == user + suffix


def test_strip_no_matching_blocks_does_not_normalize_user_text() -> None:
    user = "User text.  \n\n\n\n\nFooter.  \r\n\r\n\r\n"
    assert strip_rule_blocks(user) == user
    assert strip_rule_blocks(user, {"absent"}) == user


def test_removal_preserves_unowned_whitespace_only_file(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    user = b" \t\r\n\r\n\r\n"
    agents.write_bytes(user)
    upsert_rule_block(agents, "base", "Body.")
    assert remove_codex_rule_blocks(agents, "base") is True
    assert agents.read_bytes() == user
    assert remove_codex_rule_blocks(agents, "base") is False


@pytest.mark.parametrize(
    "blocks",
    [
        [],
        {"../../AGENTS.md": ["base"]},
        {"/tmp/AGENTS.md": ["base"]},
        {"src/other.md": ["base"]},
        {"src/**/AGENTS.md": ["base"]},
        {"AGENTS.md": "base"},
        {"AGENTS.md": [1]},
        {"AGENTS.md": ["bad name"]},
    ],
)
@pytest.mark.parametrize("target", [Target.CODEX, Target.DSH])
def test_invalid_local_protection_fails_closed(
    tmp_path: Path, blocks: object, target: Target
) -> None:
    root = tmp_path / "project"
    path = (
        registry_path(root)
        if target is Target.CODEX
        else project_layout(root).local_registry_path
    )
    _registry(path, blocks)
    before = path.read_bytes()
    with pytest.raises(ConfigError):
        project_instruction_plan([], [], root, tmp_path / "catalog")
    assert path.read_bytes() == before


def test_registry_symlink_escape_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "project"
    outside = tmp_path / "outside"
    outside.mkdir()
    _registry(project_layout(root).local_registry_path, {"linked/AGENTS.md": ["base"]})
    (root / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ConfigError, match="outside project"):
        project_instruction_plan([], [], root, tmp_path / "catalog")
    assert list(outside.iterdir()) == []


def test_project_and_directory_symlink_aliases_share_canonical_keys(
    tmp_path: Path,
) -> None:
    root = tmp_path / "physical-project"
    root.mkdir()
    alias = tmp_path / "project-alias"
    alias.symlink_to(root, target_is_directory=True)
    physical = root / "physical-src"
    physical.mkdir()
    (root / "src-alias").symlink_to(physical, target_is_directory=True)
    catalog = tmp_path / "catalog"
    _rule(catalog / "rules", "base")
    _rule(catalog / "rules", "scoped", 'paths: ["src-alias"]')
    _registry(registry_path(alias), {"src-alias/AGENTS.md": ["codex-local"]})
    _registry(
        project_layout(alias).local_registry_path,
        {"physical-src/AGENTS.md": ["dsh-local"], "AGENTS.md": ["root-local"]},
    )
    plan = project_instruction_plan(
        parse_elements(["rule:base", "rule:scoped"]),
        [Target.CODEX, Target.DSH],
        alias,
        catalog,
    )
    assert plan.project_root == root
    assert plan.wanted_blocks == {
        root / "AGENTS.md": {"base"},
        physical / "AGENTS.md": {"scoped"},
    }
    assert plan.keep_blocks == {
        root / "AGENTS.md": {"base", "root-local"},
        physical / "AGENTS.md": {"scoped", "codex-local", "dsh-local"},
    }
    assert plan.blocks[0].contributors == frozenset({Target.CODEX, Target.DSH})
    assert plan.removable_names(
        alias / "src-alias" / "AGENTS.md", ["scoped", "codex-local", "orphan"]
    ) == {"orphan"}
    assert plan.removable_names(alias / "AGENTS.md", ["base", "root-local"]) == set()
    assert not (physical / "AGENTS.md").exists()


def test_in_project_file_symlink_does_not_claim_foreign_markdown(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    foreign = root / "user.md"
    foreign.write_bytes(b"User-owned.  \r\n")
    (root / "AGENTS.md").symlink_to(foreign)
    catalog = tmp_path / "catalog"
    _rule(catalog / "rules", "base")
    with pytest.raises(ElementError, match="symlinked shared AGENTS.md"):
        project_instruction_plan(
            parse_elements(["rule:base"]), [Target.DSH], root, catalog
        )
    assert foreign.read_bytes() == b"User-owned.  \r\n"


@pytest.mark.parametrize("raw", ["{", "[]", '{"rule_blocks": null}'])
@pytest.mark.parametrize("target", [Target.CODEX, Target.DSH])
def test_malformed_registry_blocks_destructive_plan(
    tmp_path: Path, raw: str, target: Target
) -> None:
    root = tmp_path / "project"
    path = (
        registry_path(root)
        if target is Target.CODEX
        else project_layout(root).local_registry_path
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ConfigError):
        project_instruction_plan([], [], root, tmp_path / "catalog")
    assert path.read_text(encoding="utf-8") == raw


def test_unrelated_registry_fields_are_not_interpreted(tmp_path: Path) -> None:
    root = tmp_path / "project"
    for path in (registry_path(root), project_layout(root).local_registry_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '{"source_records": {"producer_specific": true}}', encoding="utf-8"
        )
    plan = project_instruction_plan([], [], root, tmp_path / "catalog")
    assert plan.protected_blocks == {}


def test_catalog_scoped_symlink_escape_fails_before_writing(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    _rule(catalog / "rules", "escape", 'paths: ["linked"]')
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ElementError, match="outside project"):
        project_instruction_plan(
            parse_elements(["rule:escape"]), [Target.CODEX], root, catalog
        )
    assert list(outside.iterdir()) == []


def test_catalog_scoped_escape_fails_before_writing(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    _rule(catalog / "rules", "escape", 'paths: ["../outside"]')
    root = tmp_path / "project"
    with pytest.raises(ElementError, match="outside project"):
        project_instruction_plan(
            parse_elements(["rule:escape"]), [Target.CODEX], root, catalog
        )
    assert not root.exists()


def test_removable_names_refuses_foreign_candidates(tmp_path: Path) -> None:
    root = tmp_path / "project"
    plan = project_instruction_plan([], [], root, tmp_path / "catalog")
    with pytest.raises(ElementError, match="outside project"):
        plan.removable_names(tmp_path / "outside" / "AGENTS.md", ["base"])


def test_foreign_symlinked_markdown_is_not_modified(tmp_path: Path) -> None:
    foreign = tmp_path / "foreign.md"
    foreign.write_bytes(b"User content.  \r\n\r\n")
    agents = tmp_path / "AGENTS.md"
    agents.symlink_to(foreign)
    with pytest.raises(ElementError, match="symlinked"):
        upsert_rule_block(agents, "base", "Body")
    with pytest.raises(ElementError, match="symlinked"):
        remove_codex_rule_blocks(agents, "base")
    assert foreign.read_bytes() == b"User content.  \r\n\r\n"

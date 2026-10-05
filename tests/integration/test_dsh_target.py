"""DSH installs preserve native bundles and prove ownership before mutation."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from ai_dotfiles.core.agents_md import upsert_rule_block
from ai_dotfiles.core.dsh_audit import (
    DSH_AUDIT_ROW_ID,
    DSH_BRIDGE_ROW_ID,
    audit_module_text,
    bridge_module_text,
)
from ai_dotfiles.core.dsh_install import (
    DshResource,
    apply_dsh_install,
    audit_path,
    collect_dsh_elements,
    output_drift,
    plan_dsh_install,
    preflight_dsh_install,
    read_dsh_inventory,
    verify_dsh_owned_output,
)
from ai_dotfiles.core.dsh_layout import DshLayout, global_layout, project_layout
from ai_dotfiles.core.dsh_permissions import translate_permissions
from ai_dotfiles.core.dsh_render import (
    render_agent,
    render_rule,
    validate_skill,
)
from ai_dotfiles.core.elements import parse_elements
from ai_dotfiles.core.errors import ConfigError, ElementError, LinkError
from ai_dotfiles.core.targets import Target
from tests.integration.test_dsh_bridge import (
    bridge_native_runtime as _bridge_native_runtime,
)

# Expose the original fixture directly: plugin registration depends on collection
# order when the plugin module is itself a collected test module.
bridge_native_runtime = _bridge_native_runtime
pytestmark = pytest.mark.integration


def _file(path: Path, content: str = "support\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _skill(path: Path, description: str = "Native skill") -> Path:
    _file(
        path / "SKILL.md",
        f"---\nname: bundle\ndescription: {description}\n---\n"
        "\nLiteral {{ value }}\n",
    )
    script = _file(path / "scripts" / "run.sh", "#!/bin/sh\necho native\n")
    script.chmod(0o751)
    _file(path / "references" / "guide.txt", "source guide\n")
    (path / "empty").mkdir()
    return path


def _layout(tmp_path: Path, scope: str) -> DshLayout:
    if scope == "global":
        return global_layout(tmp_path / "dsh-home")
    root = tmp_path / "project"
    root.mkdir(exist_ok=True)
    return project_layout(root)


def _tree_bytes(root: Path) -> dict[str, tuple[bytes | str, int]]:
    data: dict[str, tuple[bytes | str, int]] = {}
    if not root.exists():
        return data
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            data[str(path.relative_to(root))] = (
                os.readlink(path),
                path.lstat().st_mtime_ns,
            )
        elif path.is_file():
            data[str(path.relative_to(root))] = (
                path.read_bytes(),
                path.stat().st_mtime_ns,
            )
    return data


@pytest.mark.parametrize("scope", ["project", "global"])
@pytest.mark.parametrize("mode", ["link", "copy"])
def test_full_native_bundle_both_scopes(tmp_path: Path, scope: str, mode: str) -> None:
    source = _skill(tmp_path / "catalog" / "skills" / "bundle", "x" * 2400)
    layout = _layout(tmp_path, scope)
    plan = plan_dsh_install(
        layout, skills=[validate_skill(source / "SKILL.md")], mode=mode
    )
    assert not layout.dsh_dir.exists()
    assert not preflight_dsh_install(plan).records
    result = apply_dsh_install(plan)
    target = layout.skills_dir / "bundle"
    assert target.is_symlink() == (mode == "link")
    assert (target / "SKILL.md").read_bytes() == (source / "SKILL.md").read_bytes()
    assert (target / "references" / "guide.txt").read_bytes() == b"source guide\n"
    assert (target / "scripts" / "run.sh").stat().st_mode & 0o777 == 0o751
    assert (target / "empty").is_dir()
    assert (source / "SKILL.md").read_text().count("x") == 2400
    record = result.inventory.records["skills/bundle"]
    assert "references/guide.txt" in record["source_inventory"]
    assert "empty" in record["source_inventory"]
    assert record["mode"] == mode
    assert record["provenance"][0]["generator"] == 1
    assert record["generators"] == {"install": 2, "render": 1}
    assert layout.bridge_path.read_text() == bridge_module_text()
    assert audit_path(layout).read_text() == audit_module_text()
    assert not layout.config_path.exists()
    assert not layout.patch_path.exists()
    assert not layout.hooks_path.exists()
    assert not (tmp_path / "project" / ".claude").exists()
    assert read_dsh_inventory(layout) == result.inventory
    before = _tree_bytes(layout.dsh_dir)
    assert apply_dsh_install(plan).changed_paths == ()
    assert before == _tree_bytes(layout.dsh_dir)


@pytest.mark.parametrize("mode", ["link", "copy"])
def test_support_tree_drift_and_generator_drift(tmp_path: Path, mode: str) -> None:
    source = _skill(tmp_path / "catalog" / "bundle")
    layout = _layout(tmp_path, "project")

    def plan():
        return plan_dsh_install(
            layout, skills=[validate_skill(source / "SKILL.md")], mode=mode
        )

    original = plan()
    first = apply_dsh_install(original)
    previous = first.inventory.records["skills/bundle"]
    source_sha = previous["provenance"][0]["source_sha256"]
    _file(source / "references" / "guide.txt", "changed support\n")
    (source / "scripts" / "run.sh").chmod(0o700)
    (source / "empty").rmdir()
    _file(source / "assets" / "new.txt", "new resource\n")
    fresh = plan()
    skill_output = next(
        output for output in fresh.outputs if output.path.parent == layout.skills_dir
    )
    assert output_drift(skill_output, previous) == ("source changed",)
    assert skill_output.provenance[0].source_sha256 == source_sha
    registry_before = layout.provenance_path.read_bytes()
    assert read_dsh_inventory(layout).records["skills/bundle"] == previous
    assert layout.provenance_path.read_bytes() == registry_before
    refreshed = apply_dsh_install(fresh)
    assert (
        layout.skills_dir / "bundle" / "assets" / "new.txt"
    ).read_text() == "new resource\n"
    assert not (layout.skills_dir / "bundle" / "empty").exists()
    assert (
        refreshed.inventory.records["skills/bundle"]["source_tree_sha256"]
        != previous["source_tree_sha256"]
    )
    if mode == "link":
        assert layout.skills_dir / "bundle" not in refreshed.changed_paths
    else:
        assert layout.skills_dir / "bundle" in refreshed.changed_paths
    data = json.loads(layout.provenance_path.read_text())
    data["records"]["skills/bundle"]["generators"]["install"] = 0
    layout.provenance_path.write_text(json.dumps(data))
    old = read_dsh_inventory(layout).records["skills/bundle"]
    assert "generator changed" in output_drift(skill_output, old)
    apply_dsh_install(fresh)
    assert (
        read_dsh_inventory(layout).records["skills/bundle"]["generators"]["install"]
        == 2
    )


@pytest.mark.parametrize("old,new", [("copy", "link"), ("link", "copy")])
def test_owned_mode_transition_without_backup(
    tmp_path: Path, old: str, new: str
) -> None:
    source = _skill(tmp_path / "catalog" / "bundle")
    layout = _layout(tmp_path, "project")
    render = validate_skill(source / "SKILL.md")
    apply_dsh_install(plan_dsh_install(layout, skills=[render], mode=old))
    apply_dsh_install(plan_dsh_install(layout, skills=[render], mode=new))
    assert (layout.skills_dir / "bundle").is_symlink() == (new == "link")
    assert not (layout.owned_dir / "unused-backup").exists()
    assert (source / "SKILL.md").exists()


@pytest.mark.parametrize("collision", ["file", "directory", "link", "dangling"])
@pytest.mark.parametrize("destination", ["skill", "bridge", "audit", "registry"])
def test_foreign_collision_preflights_entire_plan(
    tmp_path: Path, collision: str, destination: str
) -> None:
    source = _skill(tmp_path / "catalog" / "bundle")
    layout = _layout(tmp_path, "project")
    plan = plan_dsh_install(layout, skills=[validate_skill(source / "SKILL.md")])
    target = {
        "skill": layout.skills_dir / "bundle",
        "bridge": layout.bridge_path,
        "audit": audit_path(layout),
        "registry": layout.provenance_path,
    }[destination]
    target.parent.mkdir(parents=True, exist_ok=True)
    if collision == "file":
        target.write_text("user content\n")
    elif collision == "directory":
        _file(target / "user.txt", "user content\n")
    elif collision == "link":
        target.symlink_to(_file(tmp_path / "foreign", "user content\n"))
    else:
        target.symlink_to(tmp_path / "absent")
    before = _tree_bytes(tmp_path)
    with pytest.raises((LinkError, ConfigError)):
        apply_dsh_install(plan)
    assert before == _tree_bytes(tmp_path)


@pytest.mark.parametrize("parent", [".dsh", "skills", "ai-dotfiles", "resources"])
def test_symlinked_parent_never_escapes(tmp_path: Path, parent: str) -> None:
    source = _skill(tmp_path / "catalog" / "bundle")
    layout = _layout(tmp_path, "project")
    path = {
        ".dsh": layout.dsh_dir,
        "skills": layout.skills_dir,
        "ai-dotfiles": layout.owned_dir,
        "resources": layout.resources_dir,
    }[parent]
    foreign = tmp_path / "outside"
    foreign.mkdir()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(foreign, target_is_directory=True)
    before = _tree_bytes(tmp_path)
    with pytest.raises(LinkError, match="symlinked DSH parent"):
        plan_dsh_install(layout, skills=[validate_skill(source / "SKILL.md")])
    assert before == _tree_bytes(tmp_path)


@pytest.mark.parametrize(
    "change", ["add-file", "add-dir", "add-link", "edit", "replace-link"]
)
def test_unowned_or_modified_copy_descendants_survive(
    tmp_path: Path, change: str
) -> None:
    source = _skill(tmp_path / "catalog" / "bundle")
    layout = _layout(tmp_path, "project")
    plan = plan_dsh_install(
        layout, skills=[validate_skill(source / "SKILL.md")], mode="copy"
    )
    apply_dsh_install(plan)
    target = layout.skills_dir / "bundle"
    if change == "add-file":
        _file(target / "user.txt")
    elif change == "add-dir":
        (target / "user-dir").mkdir()
    elif change == "add-link":
        (target / "user-link").symlink_to(tmp_path / "absent")
    elif change == "edit":
        _file(target / "references" / "guide.txt", "user changed\n")
    else:
        (target / "references" / "guide.txt").unlink()
        (target / "references" / "guide.txt").symlink_to(tmp_path / "absent")
    before = _tree_bytes(tmp_path)
    with pytest.raises(LinkError, match="Foreign/modified data"):
        apply_dsh_install(plan)
    with pytest.raises(LinkError):
        verify_dsh_owned_output(layout, "skills/bundle")
    assert before == _tree_bytes(tmp_path)


def test_owned_missing_resource_restores_and_foreign_link_refuses(
    tmp_path: Path,
) -> None:
    source = _skill(tmp_path / "catalog" / "bundle")
    layout = _layout(tmp_path, "project")
    plan = plan_dsh_install(
        layout, skills=[validate_skill(source / "SKILL.md")], mode="copy"
    )
    apply_dsh_install(plan)
    target = layout.skills_dir / "bundle"
    (target / "references" / "guide.txt").unlink()
    assert verify_dsh_owned_output(layout, "skills/bundle")
    apply_dsh_install(plan)
    assert (target / "references" / "guide.txt").exists()
    assert not verify_dsh_owned_output(layout, "skills/user")
    with pytest.raises(LinkError, match="outside"):
        verify_dsh_owned_output(layout, "../outside")


def test_link_text_ownership_does_not_adopt_foreign_same_catalog_link(
    tmp_path: Path,
) -> None:
    source = _skill(tmp_path / "catalog" / "bundle")
    layout = _layout(tmp_path, "project")
    target = layout.skills_dir / "bundle"
    target.parent.mkdir(parents=True)
    target.symlink_to(source)
    plan = plan_dsh_install(layout, skills=[validate_skill(source / "SKILL.md")])
    with pytest.raises(LinkError, match="Foreign DSH destination"):
        apply_dsh_install(plan)
    target.unlink()
    apply_dsh_install(plan)
    target.unlink()
    target.symlink_to(tmp_path / "absent")
    before = layout.provenance_path.read_bytes()
    assert "output changed" in output_drift(
        next(o for o in plan.outputs if o.path == target),
        read_dsh_inventory(layout).records["skills/bundle"],
    )
    with pytest.raises(LinkError, match="Foreign/modified"):
        apply_dsh_install(plan)
    assert target.is_symlink()
    assert layout.provenance_path.read_bytes() == before


def test_catalog_collection_materializes_independent_domain_resources(
    tmp_path: Path,
) -> None:
    catalog = tmp_path / "catalog"
    domain = catalog / "example"
    _skill(domain / "skills" / "bundle")
    _file(
        domain / "agents" / "writer.md",
        "---\nname: writer\ndescription: Literal {{ x }}\n"
        "tools: [Read, Bash]\ndisallowedTools: [Write]\n"
        "model: sonnet\n---\n\nDo {{ exactly }} this.\n",
    )
    _file(domain / "rules" / "always.md", "---\nalways_on: true\n---\nShared rule.\n")
    _file(
        domain / "rules" / "literal.md",
        "---\ndescription: Literal\n---\n\nKeep {{ rule }}.\n",
    )
    _file(
        domain / "rules" / "paths.md",
        "---\npaths: [src]\nalways_on: true\n---\nScoped rule.\n",
    )
    handler = _file(domain / "hooks" / "handler.sh", "#!/bin/sh\nexit 0\n")
    handler.chmod(0o751)
    _file(domain / "helpers" / "dependency.json", '{"support": true}\n')
    _file(domain / "dsh.fragment.json", "[]\n")
    layout = _layout(tmp_path, "project")
    _file(layout.root_agents_md, "User text\r\n")
    plan = collect_dsh_elements(
        parse_elements(["@example", "@example"]),
        layout,
        catalog,
        targets=(Target.CODEX, Target.DSH),
    )
    result = apply_dsh_install(plan)
    assert len(plan.resources) == 1
    installed_domain = layout.resources_dir / "domains" / "example"
    assert (installed_domain / "hooks" / "handler.sh").stat().st_mode & 0o777 == 0o751
    assert (installed_domain / "helpers" / "dependency.json").read_bytes() == (
        domain / "helpers" / "dependency.json"
    ).read_bytes()
    assert (installed_domain / "dsh.fragment.json").read_text() == "[]\n"
    assert not (layout.project_root / ".claude").exists()
    assert len(plan.ready_agents) == 1
    assert len(plan.literal_rules) == len(plan.shared_rules) == 1
    assert any(item.code == "PATH_ACTIVATION_UNSUPPORTED" for item in plan.diagnostics)
    text = layout.root_agents_md.read_bytes().decode()
    assert text.startswith("User text\r\n")
    assert text.count("rule:always START") == 1
    assert "Literal" not in text and "Scoped" not in text
    assert result.inventory.rule_blocks == {"AGENTS.md": ["always"]}
    row = plan.native_rows()[0]
    assert row["id"] == "ai-dotfiles-agent-writer"
    assert row["config"]["toolFilter"] == {
        "allow": ["read", "read_image", "bash"],
        "deny": ["write"],
    }
    assert row["config"]["persona"] == "\nDo {{ exactly }} this.\n"
    bridge = plan.bridge_config()
    assert bridge["agents"][0]["description"] == "Literal {{ x }}"
    assert bridge["rules"][0]["body"] == "\nKeep {{ rule }}.\n"
    assert {DSH_BRIDGE_ROW_ID, DSH_AUDIT_ROW_ID, row["id"]} <= set(
        plan.audit_requirements().required_ids
    )
    assert (
        next(row for row in plan.native_rows() if row["id"] == DSH_BRIDGE_ROW_ID)[
            "name"
        ]
        == layout.bridge_path.as_uri()
    )
    assert len(result.inventory.source_records) == 5
    assert any(
        data["status"] == "MANUAL" for data in result.inventory.source_records.values()
    )
    assert apply_dsh_install(plan).changed_paths == ()
    _file(domain / "helpers" / "dependency.json", "changed\n")
    refreshed = collect_dsh_elements(parse_elements(["@example"]), layout, catalog)
    resource_output = next(o for o in refreshed.outputs if o.path == installed_domain)
    key = str(installed_domain.relative_to(layout.dsh_dir))
    assert "source changed" in output_drift(
        resource_output, result.inventory.records[key]
    )
    apply_dsh_install(refreshed)
    assert (installed_domain / "helpers" / "dependency.json").read_text() == "changed\n"


def test_ready_retry_of_deferred_metadata_and_manual_restriction(
    tmp_path: Path,
) -> None:
    catalog = tmp_path / "catalog"
    source = _skill(catalog / "skills" / "bundle")
    _file(
        source / "SKILL.md",
        "---\nname: bundle\ndescription: |\n  Native multiline\n"
        "  description\n---\nUnchanged skill body.\n",
    )
    bad_agent = _file(
        catalog / "agents" / "bad.md",
        "---\nname: bad\ndescription: Bad\ntools: [Task]\n---\n"
        "Do not drop restriction.\n",
    )
    layout = _layout(tmp_path, "project")
    elements = parse_elements(["skill:bundle", "agent:bad"])
    deferred = collect_dsh_elements(elements, layout, catalog)
    assert deferred.skills[0].status == "DEFERRED"
    assert deferred.agents[0].status == "MANUAL"
    apply_dsh_install(deferred)
    assert not (layout.skills_dir / "bundle").exists()
    assert not deferred.ready_agents
    assert deferred.bridge_config()["agents"] == []
    ready = collect_dsh_elements(
        elements,
        layout,
        catalog,
        native_frontmatter={
            source
            / "SKILL.md": {
                "name": "bundle",
                "description": "Native multiline\ndescription\n",
            }
        },
    )
    assert ready.skills[0].status == "READY"
    apply_dsh_install(ready)
    assert (layout.skills_dir / "bundle" / "SKILL.md").read_bytes() == (
        source / "SKILL.md"
    ).read_bytes()
    assert "Do not drop restriction" in bad_agent.read_text()
    assert {
        value["status"] for value in read_dsh_inventory(layout).source_records.values()
    } == {"READY", "MANUAL"}
    assert not layout.config_path.exists()


def test_blocked_permissions_preserved_without_partial_activation(
    tmp_path: Path,
) -> None:
    layout = _layout(tmp_path, "project")
    source = _file(tmp_path / "policy.md", "Policy source\n")
    provenance = render_rule(source).provenance
    policy = translate_permissions({"deny": ["Bash", "Task"]}, provenance=provenance)
    plan = plan_dsh_install(layout, permissions=policy)
    assert plan.permissions.blocked
    assert plan.permissions.deny == ("bash",)
    apply_dsh_install(plan)
    assert any(d.code == "PERMISSION_UNMAPPED" for d in plan.diagnostics)
    with pytest.raises(ConfigError, match="blocked DSH permissions"):
        plan.native_rows()
    assert not layout.patch_path.exists()


@pytest.mark.parametrize("scope", ["project", "global"])
def test_ready_shared_only_and_existing_shared_block_coalesces(
    tmp_path: Path, scope: str
) -> None:
    layout = _layout(tmp_path, scope)
    source = _file(tmp_path / "always.md", "---\nalways_on: true\n---\nShared.\n")
    upsert_rule_block(layout.root_agents_md, "always", "Shared.")
    before = (
        layout.root_agents_md.read_bytes(),
        layout.root_agents_md.stat().st_mtime_ns,
    )
    plan = plan_dsh_install(layout, rules=[render_rule(source)])
    apply_dsh_install(plan)
    assert (
        layout.root_agents_md.read_bytes(),
        layout.root_agents_md.stat().st_mtime_ns,
    ) == before
    _file(source, "---\nalways_on: true\nunknown: restrict\n---\nCannot broaden.\n")
    manual = plan_dsh_install(layout, rules=[render_rule(source)])
    assert manual.rules[0].status == "MANUAL"
    apply_dsh_install(manual)
    assert (
        layout.root_agents_md.read_bytes(),
        layout.root_agents_md.stat().st_mtime_ns,
    ) == before


@pytest.mark.parametrize("registry", ["dsh", "codex"])
def test_local_protection_and_symlinked_registry_refusal(
    tmp_path: Path, registry: str
) -> None:
    layout = _layout(tmp_path, "project")
    root = layout.project_root
    source = _file(tmp_path / "always.md", "---\nalways_on: true\n---\nCatalog rule.\n")
    local = (
        layout.local_registry_path
        if registry == "dsh"
        else root / ".codex" / ".ai-dotfiles-local.json"
    )
    _file(local, json.dumps({"rule_blocks": {"AGENTS.md": ["always"]}}))
    upsert_rule_block(layout.root_agents_md, "always", "Local rule.")
    plan = plan_dsh_install(layout, rules=[render_rule(source)])
    before = _tree_bytes(tmp_path)
    with pytest.raises(LinkError, match="locally protected"):
        apply_dsh_install(plan)
    assert before == _tree_bytes(tmp_path)
    local.unlink()
    local.symlink_to(tmp_path / "absent")
    with pytest.raises(LinkError, match="symlinked.*registry"):
        plan_dsh_install(layout, rules=[render_rule(source)])


@pytest.mark.parametrize(
    "malformation", ["missing-end", "duplicate", "body-edit", "no-sha"]
)
def test_foreign_modified_shared_block_fails_before_skill_write(
    tmp_path: Path, malformation: str
) -> None:
    layout = _layout(tmp_path, "project")
    source = _file(tmp_path / "always.md", "---\nalways_on: true\n---\nShared.\n")
    skill = _skill(tmp_path / "catalog" / "bundle")
    upsert_rule_block(layout.root_agents_md, "always", "Shared.")
    text = layout.root_agents_md.read_text()
    if malformation == "missing-end":
        text = text.replace("<!-- ai-dotfiles:rule:always END -->", "")
    elif malformation == "duplicate":
        text += text
    elif malformation == "body-edit":
        text = text.replace("Shared.", "User edit.")
    else:
        text = "\n".join(line for line in text.splitlines() if "sha256:" not in line)
    layout.root_agents_md.write_text(text)
    plan = plan_dsh_install(
        layout, skills=[validate_skill(skill / "SKILL.md")], rules=[render_rule(source)]
    )
    before = _tree_bytes(tmp_path)
    with pytest.raises(LinkError):
        apply_dsh_install(plan)
    assert before == _tree_bytes(tmp_path)


def test_global_install_does_not_scan_home_or_modify_native_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = _layout(tmp_path, "global")
    native = [
        _file(layout.dsh_dir / "home.yaml", "User native profile\n"),
        _file(layout.dsh_dir / "package.json", '{"user": true}\n'),
        _file(layout.dsh_dir / "profiles" / "custom.yaml", "Custom\n"),
        _file(tmp_path / "home" / "valuable.txt", "Valuable\n"),
        _file(layout.skills_dir / "foreign" / "SKILL.md", "Foreign\n"),
        _file(layout.resources_dir / "foreign.txt", "Foreign\n"),
    ]
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in native}
    source = _skill(tmp_path / "catalog" / "bundle")
    monkeypatch.setattr(
        Path,
        "rglob",
        lambda *args, **kwargs: pytest.fail("No recursive HOME/owned-root scan"),
    )
    plan = plan_dsh_install(
        layout, skills=[validate_skill(source / "SKILL.md")], mode="copy"
    )
    apply_dsh_install(plan)
    assert before == {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in native
    }
    assert apply_dsh_install(plan).changed_paths == ()


@pytest.mark.parametrize("bad", ["../escape", "/absolute", "."])
def test_resource_paths_are_bounded_and_full_resource_linked(
    tmp_path: Path, bad: str
) -> None:
    layout = _layout(tmp_path, "project")
    source = _file(tmp_path / "support.sh")
    source.chmod(0o640)
    provenance = render_rule(source).provenance
    with pytest.raises((ConfigError, LinkError)):
        plan_dsh_install(layout, resources=[DshResource(source, Path(bad), provenance)])
    plan = plan_dsh_install(
        layout,
        resources=[
            DshResource(source, Path("custom") / "support.sh", provenance, "link")
        ],
    )
    result = apply_dsh_install(plan)
    assert (layout.resources_dir / "custom" / "support.sh").resolve() == source
    record = result.inventory.records["ai-dotfiles/resources/custom/support.sh"]
    assert record["provenance"] == [provenance.as_dict()]
    assert record["mode"] == "link"
    assert source.stat().st_mode & 0o777 == 0o640
    assert apply_dsh_install(plan).changed_paths == ()
    assert (
        apply_dsh_install(
            plan_dsh_install(
                layout,
                resources=[
                    DshResource(
                        source, Path("custom") / "support.sh", provenance, "link"
                    )
                ],
            )
        ).changed_paths
        == ()
    )


def test_collision_between_selected_sources_is_read_only(tmp_path: Path) -> None:
    first = _skill(tmp_path / "one" / "bundle")
    second = _skill(tmp_path / "two" / "bundle")
    layout = _layout(tmp_path, "project")
    with pytest.raises(LinkError, match="Overlapping"):
        plan_dsh_install(
            layout,
            skills=[
                validate_skill(first / "SKILL.md"),
                validate_skill(second / "SKILL.md"),
            ],
        )
    assert not layout.dsh_dir.exists()
    a = _file(
        tmp_path / "one" / "a.md", "---\nname: same\ndescription: Same\n---\nOne\n"
    )
    b = _file(
        tmp_path / "two" / "b.md", "---\nname: same\ndescription: Same\n---\nTwo\n"
    )
    with pytest.raises(ConfigError, match="Duplicate managed DSH agent"):
        plan_dsh_install(layout, agents=[render_agent(a), render_agent(b)])
    assert not layout.dsh_dir.exists()


def test_source_changed_between_render_plan_and_apply_fails_read_only(
    tmp_path: Path,
) -> None:
    source = _skill(tmp_path / "catalog" / "bundle")
    layout = _layout(tmp_path, "project")
    render = validate_skill(source / "SKILL.md")
    plan = plan_dsh_install(layout, skills=[render], mode="copy")
    _file(source / "scripts" / "run.sh", "new support\n")
    with pytest.raises(LinkError, match="after planning"):
        apply_dsh_install(plan)
    assert not layout.dsh_dir.exists()
    _file(source / "SKILL.md", "Changed skill\n")
    with pytest.raises(LinkError, match="after rendering"):
        plan_dsh_install(layout, skills=[render])


def test_generated_modules_and_sources_have_generator_drift(tmp_path: Path) -> None:
    layout = _layout(tmp_path, "project")
    source = _file(tmp_path / "literal.md", "Rule {{ body }}\n")
    plan = plan_dsh_install(layout, rules=[render_rule(source)])
    result = apply_dsh_install(plan)
    module = next(o for o in plan.outputs if o.path == layout.bridge_path)
    record = result.inventory.records["ai-dotfiles/bridge.mjs"]
    assert record["provenance"][0]["origin"] == "builtin"
    assert record["provenance"][0]["element"] == "dsh-bridge"
    assert record["generators"] == {"bridge": 1}
    bumped = replace(module, generators={"bridge": 2})
    assert output_drift(bumped, record) == ("generator changed",)
    result = apply_dsh_install(
        replace(plan, outputs=tuple(bumped if o == module else o for o in plan.outputs))
    )
    assert result.inventory.records["ai-dotfiles/bridge.mjs"]["generators"] == {
        "bridge": 2
    }
    assert result.changed_paths == (layout.provenance_path,)


def test_empty_plan_retains_retired_output_inventory_for_lifecycle(
    tmp_path: Path,
) -> None:
    layout = _layout(tmp_path, "project")
    source = _skill(tmp_path / "catalog" / "bundle")
    first = apply_dsh_install(
        plan_dsh_install(layout, skills=[validate_skill(source / "SKILL.md")])
    )
    empty = apply_dsh_install(plan_dsh_install(layout))
    assert (
        empty.inventory.records["skills/bundle"]
        == first.inventory.records["skills/bundle"]
    )
    assert empty.inventory.source_records == first.inventory.source_records
    assert (layout.skills_dir / "bundle").is_symlink()
    assert verify_dsh_owned_output(layout, "skills/bundle")


@pytest.mark.parametrize("status", ["MANUAL", "DEFERRED"])
def test_previously_ready_native_skill_exposed_for_retirement(
    tmp_path: Path, status: str
) -> None:
    layout = _layout(tmp_path, "project")
    source = _skill(tmp_path / "catalog" / "skills" / "bundle")
    apply_dsh_install(
        collect_dsh_elements(
            parse_elements(["skill:bundle"]), layout, tmp_path / "catalog"
        )
    )
    text = (
        "---\nname: bundle\ndescription: Skill\nallowed-tools: Bash\n---\n"
        "Native runtime might ignore restriction.\n"
        if status == "MANUAL"
        else "---\nname: bundle\ndescription: |\n  Native valid YAML\n---\n"
        "Pending native validation.\n"
    )
    _file(source / "SKILL.md", text)
    plan = collect_dsh_elements(
        parse_elements(["skill:bundle"]), layout, tmp_path / "catalog"
    )
    assert plan.skills[0].status == status
    result = apply_dsh_install(plan)
    assert (layout.skills_dir / "bundle").is_symlink()
    assert "skills/bundle" not in plan.desired_output_keys
    assert result.retired_output_keys == ("skills/bundle",)
    assert len(plan.current_source_ids) == 1
    assert {value["status"] for value in result.inventory.source_records.values()} == {
        status
    }
    assert plan.diagnostics


@pytest.mark.parametrize("kind", ["agent", "literal", "shared"])
def test_contribution_source_change_after_plan_is_rejected(
    tmp_path: Path, kind: str
) -> None:
    layout = _layout(tmp_path, "project")
    source = _file(
        tmp_path / "element.md",
        {
            "agent": "---\nname: child\ndescription: Child\ntools: [Bash]\n"
            "---\nLiteral\n",
            "literal": "Literal rule\n",
            "shared": "---\nalways_on: true\n---\nShared rule\n",
        }[kind],
    )
    plan = (
        plan_dsh_install(layout, agents=[render_agent(source)])
        if kind == "agent"
        else plan_dsh_install(layout, rules=[render_rule(source)])
    )
    _file(source, source.read_text() + "New restriction\n")
    with pytest.raises(LinkError, match="after rendering"):
        apply_dsh_install(plan)
    assert not layout.dsh_dir.exists()
    assert not layout.root_agents_md.exists()


@pytest.mark.parametrize("error", ["missing", "unicode"])
def test_unreadable_render_source_raises_core_error(tmp_path: Path, error: str) -> None:
    layout = _layout(tmp_path, "project")
    source = _file(tmp_path / "rule.md", "Rule\n")
    rendered = render_rule(source)
    plan = plan_dsh_install(layout, rules=[rendered])
    if error == "missing":
        source.unlink()
    else:
        source.write_bytes(b"\xff\xfe")
    with pytest.raises(LinkError, match="Cannot read DSH contribution"):
        apply_dsh_install(plan)
    with pytest.raises(LinkError, match="Cannot read DSH contribution"):
        plan_dsh_install(layout, rules=[rendered])
    assert not layout.dsh_dir.exists()


def test_invalid_shared_utf8_raises_core_error_before_writes(tmp_path: Path) -> None:
    layout = _layout(tmp_path, "project")
    source = _file(tmp_path / "rule.md", "---\nalways_on: true\n---\nRule\n")
    plan = plan_dsh_install(layout, rules=[render_rule(source)])
    layout.root_agents_md.write_bytes(b"\xff\xfe")
    with pytest.raises(LinkError, match="Cannot read DSH shared instructions"):
        apply_dsh_install(plan)
    assert layout.root_agents_md.read_bytes() == b"\xff\xfe"
    assert not layout.dsh_dir.exists()


@pytest.mark.parametrize("scope", ["project", "global"])
@pytest.mark.parametrize("mode", ["link", "copy"])
def test_outer_alias_keeps_lexical_root_and_bounded_writes(
    tmp_path: Path, scope: str, mode: str
) -> None:
    physical = tmp_path / "physical"
    physical.mkdir()
    alias = tmp_path / "outer-alias"
    alias.symlink_to(physical, target_is_directory=True)
    layout = (
        project_layout(alias / "project")
        if scope == "project"
        else global_layout(alias / "dsh-home")
    )
    foreign = [
        _file(physical / "sibling.txt", "Foreign sibling\n"),
        _file(layout.dsh_dir / "home.yaml", "Native user profile\n"),
        _file(layout.skills_dir / "user" / "SKILL.md", "User skill\n"),
    ]
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in foreign}
    source = _skill(tmp_path / "catalog" / "bundle")
    plan = plan_dsh_install(
        layout, skills=[validate_skill(source / "SKILL.md")], mode=mode
    )
    result = apply_dsh_install(plan)
    assert str(layout.dsh_dir).startswith(str(alias))
    assert (
        next(row for row in plan.native_rows() if row["id"] == DSH_BRIDGE_ROW_ID)[
            "name"
        ]
        == layout.bridge_path.as_uri()
    )
    assert all(
        path.parent.resolve().is_relative_to(layout.dsh_dir.resolve())
        for path in result.changed_paths
    )
    assert (layout.skills_dir / "bundle" / "SKILL.md").read_bytes() == (
        source / "SKILL.md"
    ).read_bytes()
    assert before == {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in foreign
    }
    assert apply_dsh_install(plan).changed_paths == ()


@pytest.mark.parametrize(
    "malformation", ["schema", "key", "tree-key", "digest", "provenance", "generators"]
)
def test_malformed_ownership_registry_refuses_before_writes(
    tmp_path: Path, malformation: str
) -> None:
    layout = _layout(tmp_path, "project")
    source = _skill(tmp_path / "catalog" / "bundle")
    plan = plan_dsh_install(layout, skills=[validate_skill(source / "SKILL.md")])
    apply_dsh_install(plan)
    data = json.loads(layout.provenance_path.read_text())
    record = data["records"]["skills/bundle"]
    if malformation == "schema":
        data["schema_version"] = True
    elif malformation == "key":
        data["records"]["../escape"] = record
    elif malformation == "tree-key":
        record["output_inventory"]["../escape"] = {"kind": "directory", "mode": 0o755}
    elif malformation == "digest":
        record["source_tree_sha256"] = "wrong"
    elif malformation == "provenance":
        record["provenance"] = []
    else:
        record["generators"] = {"install": True}
    layout.provenance_path.write_text(json.dumps(data))
    before = _tree_bytes(tmp_path)
    with pytest.raises((LinkError, ConfigError)):
        apply_dsh_install(plan)
    assert before == _tree_bytes(tmp_path)


@pytest.mark.parametrize("scope", ["project", "global"])
@pytest.mark.parametrize("mode", ["link", "copy"])
def test_published_rc2_discovers_and_loads_full_native_bundle(
    tmp_path: Path, bridge_native_runtime: Path, scope: str, mode: str
) -> None:
    # Reuse the bridge's required, pinned, disposable fixture; Phase 4 owns
    # consolidation into the shared native-runtime acceptance fixtures.
    source = _skill(tmp_path / "catalog" / "bundle", "x" * 2400)
    layout = _layout(tmp_path, scope)
    apply_dsh_install(
        plan_dsh_install(
            layout, skills=[validate_skill(source / "SKILL.md")], mode=mode
        )
    )
    root = tmp_path / "native"
    root.mkdir()
    (root / "node_modules").symlink_to(
        bridge_native_runtime / "node_modules", target_is_directory=True
    )
    home = root / "home"
    home.mkdir()
    lookup = layout.project_root or root / "lookup"
    lookup.mkdir(exist_ok=True)
    native_home = layout.dsh_dir if scope == "global" else root / "user-dsh"
    config = root / "native.json"
    config.write_text(
        json.dumps(
            [
                {"id": "skill", "name": "@deepseek-ai/dsh-skill"},
                {
                    "id": "skill-filesystem",
                    "name": "@deepseek-ai/dsh-skill-filesystem",
                    "config": {
                        "dshHome": str(native_home),
                        "agentsHome": str(root / "user-agents"),
                        "watch": False,
                    },
                },
            ]
        )
    )
    fixture = root / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "cwd": str(lookup),
                "target": str(layout.skills_dir / "bundle"),
                "expectedSource": "user-dsh" if scope == "global" else "project-dsh",
            }
        )
    )
    script = _file(
        root / "run.mjs",
        r"""
import assert from 'node:assert/strict';
import { readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { boot } from '@deepseek-ai/dsh-app-boot';
const fixture = JSON.parse(readFileSync(new URL('./fixture.json', import.meta.url)));
const ctx = await boot('dsh-skill-install-test',
  new URL('./native.json', import.meta.url).pathname, undefined, undefined,
  import.meta.url);
try {
  await ctx.loader.await();
  assert.ok(ctx.skills, 'native skill service must be loaded');
  const listed = await ctx.skills.list({ cwd: fixture.cwd });
  assert.equal(listed.length, 1);
  assert.equal(listed[0].name, 'bundle');
  assert.equal(listed[0].source, fixture.expectedSource);
  assert.equal(listed[0].description, 'x'.repeat(2400));
  const loaded = await ctx.skills.get('bundle', { cwd: fixture.cwd });
  assert.ok(loaded);
  assert.equal(loaded.content, 'Literal {{ value }}');
  assert.deepEqual(loaded.invocation, { modelInvocable: true, userInvocable: true });
  assert.deepEqual(loaded.resourceBase, { kind: 'directory', path: fixture.target });
  assert.equal(readFileSync(join(loaded.resourceBase.path,
    'references/guide.txt'), 'utf8'), 'source guide\n');
  assert.equal(statSync(join(loaded.resourceBase.path,
    'scripts/run.sh')).mode & 0o777, 0o751);
  console.log(JSON.stringify({ source: loaded.source, fullBundle: true }));
} finally { await ctx.fiber.dispose(); }
""",
    )
    result = subprocess.run(
        ["node", str(script)],
        cwd=root,
        env={
            "PATH": os.environ["PATH"],
            "HOME": str(home),
            "DSH_HOME": str(native_home),
            "DSH_AGENTS_HOME": str(root / "user-agents"),
            "XDG_CONFIG_HOME": str(root / "xdg"),
            "npm_config_cache": str(root / "npm-cache"),
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {
        "source": "user-dsh" if scope == "global" else "project-dsh",
        "fullBundle": True,
    }
    assert not layout.config_path.exists()
    assert not (layout.dsh_dir / "home.yaml").exists()
    assert not (layout.dsh_dir / "package.json").exists()


def test_new_local_protection_after_planning_is_respected(tmp_path: Path) -> None:
    layout = _layout(tmp_path, "project")
    source = _file(tmp_path / "always.md", "---\nalways_on: true\n---\nCatalog rule\n")
    plan = plan_dsh_install(layout, rules=[render_rule(source)])
    _file(
        layout.local_registry_path,
        json.dumps({"rule_blocks": {"AGENTS.md": ["always"]}}),
    )
    upsert_rule_block(layout.root_agents_md, "always", "New local rule")
    before = _tree_bytes(tmp_path)
    with pytest.raises(LinkError, match="locally protected"):
        apply_dsh_install(plan)
    assert before == _tree_bytes(tmp_path)


def test_shared_target_union_conflicts_do_not_overwrite_codex(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    source = _file(
        catalog / "rules" / "always.md", "---\nalways_on: true\n---\nCodex rule\n"
    )
    layout = _layout(tmp_path, "project")
    existing = collect_dsh_elements(
        parse_elements(["rule:always"]),
        layout,
        catalog,
        targets=(Target.CODEX, Target.DSH),
    )
    other = _file(tmp_path / "always.md", "---\nalways_on: true\n---\nDSH rule\n")
    with pytest.raises(ElementError, match="shared target union"):
        plan_dsh_install(
            layout, rules=[render_rule(other)], instructions=existing.instructions
        )
    assert not layout.dsh_dir.exists()
    assert source.read_text().endswith("Codex rule\n")

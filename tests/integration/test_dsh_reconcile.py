"""Fresh-source drift, exact local custody and check-mode filesystem invariants."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from ai_dotfiles.core import agents_md
from ai_dotfiles.core.dsh_install import (
    collect_dsh_elements,
    preflight_dsh_install,
    read_dsh_inventory,
    verify_dsh_local_rule_custody,
)
from ai_dotfiles.core.dsh_layout import global_layout, project_layout
from ai_dotfiles.core.dsh_local_registry import load_dsh_local_registry
from ai_dotfiles.core.dsh_migrate import (
    DshLocalInputs,
    collect_dsh_local_inputs,
    migrate_to_dsh,
    plan_dsh_migration,
)
from ai_dotfiles.core.dsh_reconcile import (
    apply_dsh_reconciliation,
    plan_dsh_reconciliation,
    prune_dsh,
    reconcile_dsh,
    reconcile_dsh_global,
)
from ai_dotfiles.core.elements import parse_elements
from ai_dotfiles.core.errors import ConfigError, ElementError, LinkError
from ai_dotfiles.core.gitignore import collect_dsh_managed_paths, sync_gitignore
from ai_dotfiles.core.targets import Target

pytestmark = pytest.mark.integration


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    return path


def _json(path: Path, value: object) -> Path:
    return _write(path, json.dumps(value))


def _skill(root: Path, name: str = "sample") -> Path:
    return _write(
        root / "skills" / name / "SKILL.md",
        f"---\nname: {name}\ndescription: Sample\n---\nOriginal body\n",
    )


def _rule(root: Path, body: str = "Original body\n", extra: str = "") -> Path:
    return _write(
        root / ".claude/rules/local.md", f"---\nalways_on: true\n{extra}---\n{body}"
    )


def _snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    return {
        str(path.relative_to(root)): (
            path.lstat().st_mode,
            path.lstat().st_mtime_ns,
            (
                str(path.readlink())
                if path.is_symlink()
                else (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    if path.is_file()
                    else ""
                )
            ),
        )
        for path in root.rglob("*")
    }


@pytest.mark.parametrize("mode", ["link", "copy"])
def test_fresh_catalog_source_resource_and_missing_drift(
    tmp_path: Path, tmp_storage: Path, mode: str
) -> None:
    catalog = tmp_storage / "catalog"
    source = _skill(catalog)
    report = reconcile_dsh(tmp_path, ["skill:sample"], catalog, mode=mode)
    assert report.changed_paths
    assert not reconcile_dsh(
        tmp_path, ["skill:sample"], catalog, mode=mode, check_only=True
    ).drift
    _write(source.parent / "support.txt", "Changed resource\n")
    before = _snapshot(tmp_path)
    check = reconcile_dsh(
        tmp_path, ["skill:sample"], catalog, mode=mode, check_only=True
    )
    assert check.exit_code == 1
    assert any("source changed" in label for label in check.drift)
    assert _snapshot(tmp_path) == before
    reconcile_dsh(tmp_path, ["skill:sample"], catalog, mode=mode)
    assert not reconcile_dsh(
        tmp_path, ["skill:sample"], catalog, mode=mode, check_only=True
    ).drift
    (tmp_path / ".dsh/ai-dotfiles/bridge.mjs").unlink()
    assert any(
        "missing" in label
        for label in reconcile_dsh(
            tmp_path, ["skill:sample"], catalog, mode=mode, check_only=True
        ).drift
    )
    reconcile_dsh(tmp_path, ["skill:sample"], catalog, mode=mode)
    assert (tmp_path / ".dsh/ai-dotfiles/bridge.mjs").is_file()


def test_changed_own_local_rule_refreshes_without_registry_bypass(
    tmp_path: Path, tmp_storage: Path
) -> None:
    rule = _rule(tmp_path)
    _write(tmp_path / "AGENTS.md", "User instructions  \r\n")
    migrate_to_dsh(tmp_path)
    old_registry = (tmp_path / ".dsh/ai-dotfiles/local.json").read_bytes()
    _rule(tmp_path, "Changed body {{literal}}\n")
    producer = plan_dsh_migration(collect_dsh_local_inputs(tmp_path))
    with pytest.raises(LinkError, match="locally protected"):
        preflight_dsh_install(producer.install)
    plan = plan_dsh_reconciliation(
        project_layout(tmp_path), [], tmp_storage / "catalog"
    )
    assert plan.local_rule_custody == {"local": str(rule.relative_to(tmp_path))}
    assert (tmp_path / ".dsh/ai-dotfiles/local.json").read_bytes() == old_registry
    before = _snapshot(tmp_path)
    assert apply_dsh_reconciliation(plan, check_only=True).exit_code == 1
    assert _snapshot(tmp_path) == before
    apply_dsh_reconciliation(plan)
    actual = (tmp_path / "AGENTS.md").read_bytes()
    assert actual.startswith(b"User instructions  \r\n")
    assert b"Changed body {{literal}}" in actual
    assert b"Original body" not in actual
    assert not reconcile_dsh(
        tmp_path, [], tmp_storage / "catalog", check_only=True
    ).drift


@pytest.mark.parametrize("mutation", ["text", "hash", "body", "status", "activation"])
def test_custody_refuses_tampered_prior_source_records(
    tmp_path: Path, mutation: str
) -> None:
    _rule(tmp_path)
    migrate_to_dsh(tmp_path)
    path = tmp_path / ".dsh/ai-dotfiles/provenance.json"
    data = json.loads(path.read_bytes())
    prior = next(iter(data["source_records"].values()))
    if mutation == "text":
        prior["source_text"] += "tampered"
    elif mutation == "hash":
        prior["provenance"]["source_sha256"] = "f" * 64
    else:
        prior[mutation] = "tampered"
    _json(path, data)
    before = _snapshot(tmp_path)
    with pytest.raises(LinkError, match="custody"):
        verify_dsh_local_rule_custody(
            project_layout(tmp_path), "local", ".claude/rules/local.md"
        )
    assert _snapshot(tmp_path) == before


def test_custody_is_not_an_unchecked_name_set(tmp_path: Path) -> None:
    _rule(tmp_path)
    migrate_to_dsh(tmp_path)
    _rule(tmp_path, "New body\n")
    plan = plan_dsh_migration(collect_dsh_local_inputs(tmp_path))
    with pytest.raises((LinkError, ConfigError)):
        preflight_dsh_install(
            plan.install, local_rule_custody={"local": ".claude/agents/local.md"}
        )


@pytest.mark.parametrize("mutation", ["body", "duplicate", "header"])
def test_user_modified_rule_refuses_before_any_writes(
    tmp_path: Path, tmp_storage: Path, mutation: str
) -> None:
    _rule(tmp_path)
    migrate_to_dsh(tmp_path)
    path = tmp_path / "AGENTS.md"
    original = path.read_text()
    _write(
        path,
        (
            original.replace("Original body", "User edit")
            if mutation == "body"
            else (
                original + original
                if mutation == "duplicate"
                else original.replace("sha256:", "tampered:")
            )
        ),
    )
    _rule(tmp_path, "Fresh body\n")
    before = _snapshot(tmp_path)
    with pytest.raises(LinkError):
        reconcile_dsh(tmp_path, [], tmp_storage / "catalog")
    assert _snapshot(tmp_path) == before


def test_independent_codex_local_owner_blocks_conflicting_refresh(
    tmp_path: Path, tmp_storage: Path
) -> None:
    _rule(tmp_path)
    migrate_to_dsh(tmp_path)
    _json(
        tmp_path / ".codex/.ai-dotfiles-local.json",
        {"rule_blocks": {"AGENTS.md": ["local"]}},
    )
    _rule(tmp_path, "New DSH body\n")
    before = _snapshot(tmp_path)
    with pytest.raises(LinkError, match="locally protected"):
        reconcile_dsh(tmp_path, [], tmp_storage / "catalog")
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "raw",
    [
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".claude/hooks.json",
        ".mcp.json",
    ],
)
def test_new_original_after_planning_refuses_before_writes(
    tmp_path: Path, tmp_storage: Path, raw: str
) -> None:
    _rule(tmp_path)
    migrate_to_dsh(tmp_path)
    _rule(tmp_path, "New body\n")
    plan = plan_dsh_reconciliation(
        project_layout(tmp_path), [], tmp_storage / "catalog"
    )
    _json(tmp_path / raw, {})
    before = _snapshot(tmp_path)
    with pytest.raises(LinkError, match="source set changed"):
        apply_dsh_reconciliation(plan)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("filename", ["local.json", "provenance.json"])
def test_registry_changes_after_planning_refuse_before_writes(
    tmp_path: Path, tmp_storage: Path, filename: str
) -> None:
    _rule(tmp_path)
    migrate_to_dsh(tmp_path)
    _rule(tmp_path, "New body\n")
    plan = plan_dsh_reconciliation(
        project_layout(tmp_path), [], tmp_storage / "catalog"
    )
    path = tmp_path / ".dsh/ai-dotfiles" / filename
    path.write_bytes(path.read_bytes() + b"\n")
    before = _snapshot(tmp_path)
    with pytest.raises(LinkError, match="registry changed"):
        apply_dsh_reconciliation(plan)
    assert _snapshot(tmp_path) == before


def test_generator_drift_uses_fresh_desired_output_metadata(
    tmp_path: Path, tmp_storage: Path
) -> None:
    catalog = tmp_storage / "catalog"
    _skill(catalog)
    reconcile_dsh(tmp_path, ["skill:sample"], catalog)
    path = tmp_path / ".dsh/ai-dotfiles/provenance.json"
    data = json.loads(path.read_bytes())
    data["records"]["ai-dotfiles/bridge.mjs"]["generators"]["bridge"] = 999
    _json(path, data)
    before = _snapshot(tmp_path)
    report = reconcile_dsh(tmp_path, ["skill:sample"], catalog, check_only=True)
    assert any("generator changed" in label for label in report.drift)
    assert _snapshot(tmp_path) == before
    reconcile_dsh(tmp_path, ["skill:sample"], catalog)
    assert not reconcile_dsh(tmp_path, ["skill:sample"], catalog, check_only=True).drift


@pytest.mark.parametrize("transition", ["manual", "literal"])
@pytest.mark.parametrize("removed", [False, True])
def test_repeated_migrate_retains_old_shared_custody_until_retirement(
    tmp_path: Path, tmp_storage: Path, transition: str, removed: bool
) -> None:
    rule = _rule(tmp_path)
    migrate_to_dsh(tmp_path)
    if transition == "manual":
        _rule(tmp_path, "Scoped body\n", "paths: ['**/*.py']\n")
    else:
        _write(rule, "---\ndescription: Literal\n---\nLiteral body\n")
    migrate_to_dsh(tmp_path)
    inventory = read_dsh_inventory(project_layout(tmp_path))
    historical = next(iter(inventory.shared_rule_records.values()))["source_record"]
    assert historical["body"] == "Original body"
    current = next(iter(inventory.source_records.values()))
    assert current["status"] == ("MANUAL" if transition == "manual" else "READY")
    if removed:
        rule.unlink()
    before = _snapshot(tmp_path)
    report = reconcile_dsh(tmp_path, [], tmp_storage / "catalog", check_only=True)
    assert report.exit_code == 1
    assert _snapshot(tmp_path) == before
    reconcile_dsh(tmp_path, [], tmp_storage / "catalog")
    assert (
        not (tmp_path / "AGENTS.md").exists()
        or b"Original body" not in (tmp_path / "AGENTS.md").read_bytes()
    )
    assert not read_dsh_inventory(project_layout(tmp_path)).shared_rule_records
    assert not reconcile_dsh(
        tmp_path, [], tmp_storage / "catalog", check_only=True
    ).drift


def test_unproven_aggregate_env_cannot_activate_from_snapshot(
    tmp_path: Path, tmp_storage: Path
) -> None:
    from ai_dotfiles.core.settings_ownership import save_settings_ownership

    _rule(tmp_path)
    migrate_to_dsh(tmp_path)
    _json(
        tmp_path / ".claude/settings.json",
        {"permissions": {"deny": ["Bash"]}, "env": {"UNPROVEN": "original"}},
    )
    save_settings_ownership(tmp_path / ".claude", {"permissions_deny": ["Bash"]})
    before = _snapshot(tmp_path)
    inputs = collect_dsh_local_inputs(tmp_path)
    assert any("env" in source.unproven_fields for source in inputs.raw_sources)
    with pytest.raises(ConfigError, match="local .* env:"):
        reconcile_dsh(tmp_path, [], tmp_storage / "catalog")
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("scope", ["project", "global"])
def test_empty_fresh_check_creates_no_roots(tmp_path: Path, scope: str) -> None:
    catalog = tmp_path / "catalog"
    layout = (
        project_layout(tmp_path / "project")
        if scope == "project"
        else global_layout(tmp_path / "home")
    )
    before = _snapshot(tmp_path)
    report = prune_dsh(plan_dsh_reconciliation(layout, [], catalog), check_only=True)
    assert report.exit_code == 0
    assert report.changed_paths == ()
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("scope", ["project", "global"])
@pytest.mark.parametrize("disabled", [False, True])
def test_empty_or_disabled_catalog_retires_owned_only(
    tmp_path: Path, scope: str, disabled: bool
) -> None:
    catalog = tmp_path / "catalog"
    _skill(catalog)
    rule = _write(
        catalog / "rules/shared.md", "---\nalways_on: true\n---\nShared body\n"
    )
    layout = (
        project_layout(tmp_path / "project")
        if scope == "project"
        else global_layout(tmp_path / "home")
    )
    _write(layout.root_agents_md, "User bytes  \r\n")
    packages = ["skill:sample", "rule:shared"]
    prune_dsh(plan_dsh_reconciliation(layout, packages, catalog))
    foreign = _write(layout.skills_dir / "foreign/SKILL.md", "User skill\n")
    profile = _write(layout.dsh_dir / "profiles/default/cordis.yml", "User profile\n")
    user_resource = _write(layout.resources_dir / "foreign.txt", "User resource\n")
    plan = plan_dsh_reconciliation(
        layout, packages if disabled else [], catalog, include_catalog=not disabled
    )
    before = _snapshot(tmp_path)
    assert prune_dsh(plan, check_only=True).exit_code == 1
    assert _snapshot(tmp_path) == before
    prune_dsh(plan)
    inventory = read_dsh_inventory(layout)
    assert inventory.records == inventory.source_records == inventory.rule_blocks == {}
    assert not inventory.shared_rule_records
    assert foreign.read_bytes() == b"User skill\n"
    assert profile.read_bytes() == b"User profile\n"
    assert user_resource.read_bytes() == b"User resource\n"
    assert layout.root_agents_md.read_bytes() == b"User bytes  \r\n"
    assert rule.exists()
    assert not prune_dsh(
        plan_dsh_reconciliation(
            layout, packages if disabled else [], catalog, include_catalog=not disabled
        ),
        check_only=True,
    ).drift


@pytest.mark.parametrize("kind", ["skill", "agent", "command", "rule"])
def test_deleted_local_source_retires_exact_output_and_registry(
    tmp_path: Path, tmp_storage: Path, kind: str
) -> None:
    if kind == "skill":
        source = _skill(tmp_path / ".claude", "local")
        _write(source.parent / "scripts/run.sh", "#!/bin/sh\ntrue\n")
    elif kind == "rule":
        source = _rule(tmp_path)
    else:
        extra = "disable-model-invocation: true\n" if kind == "command" else ""
        source = _write(
            tmp_path
            / ".claude"
            / ("commands" if kind == "command" else "agents")
            / "local.md",
            f"---\nname: local\ndescription: Local\n{extra}---\nLocal body\n",
        )
    migrate_to_dsh(tmp_path)
    user = _write(tmp_path / ".dsh/skills/foreign/SKILL.md", "User\n")
    original = read_dsh_inventory(project_layout(tmp_path))
    if kind == "skill":
        shutil.rmtree(source.parent)
    else:
        source.unlink()
    before = _snapshot(tmp_path)
    check = reconcile_dsh(tmp_path, [], tmp_storage / "catalog", check_only=True)
    assert check.exit_code == 1
    assert _snapshot(tmp_path) == before
    reconcile_dsh(tmp_path, [], tmp_storage / "catalog")
    inventory = read_dsh_inventory(project_layout(tmp_path))
    assert inventory.records == inventory.source_records == inventory.rule_blocks == {}
    assert not inventory.shared_rule_records
    assert not load_dsh_local_registry(tmp_path).sources
    assert all(not (tmp_path / ".dsh" / key).exists() for key in original.records)
    assert user.read_bytes() == b"User\n"
    assert not reconcile_dsh(
        tmp_path, [], tmp_storage / "catalog", check_only=True
    ).drift


@pytest.mark.parametrize("mutation", ["extra", "edit", "link"])
def test_modified_retiring_output_refuses_every_write(
    tmp_path: Path, tmp_storage: Path, mutation: str
) -> None:
    catalog = tmp_storage / "catalog"
    _skill(catalog)
    mode = "link" if mutation == "link" else "copy"
    reconcile_dsh(tmp_path, ["skill:sample"], catalog, mode=mode)
    target = tmp_path / ".dsh/skills/sample"
    if mutation == "link":
        target.unlink()
        target.symlink_to(tmp_path / "foreign")
    else:
        _write(
            target / ("user.txt" if mutation == "extra" else "SKILL.md"), "User edit\n"
        )
    before = _snapshot(tmp_path)
    with pytest.raises(LinkError):
        reconcile_dsh(tmp_path, [], catalog)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("local", [False, True])
def test_dsh_retires_its_refs_while_codex_keeps_then_removes_shared_block(
    tmp_path: Path, tmp_storage: Path, local: bool
) -> None:
    catalog = tmp_storage / "catalog"
    _write(tmp_path / "AGENTS.md", "User bytes  \r\n")
    if local:
        source = _rule(tmp_path)
        name = "local"
        migrate_to_dsh(tmp_path)
        _json(
            tmp_path / ".codex/.ai-dotfiles-local.json",
            {"rule_blocks": {"AGENTS.md": [name]}},
        )
        source.unlink()
        packages: list[str] = []
    else:
        name = "shared"
        _write(catalog / "rules/shared.md", "---\nalways_on: true\n---\nShared body\n")
        packages = ["rule:shared"]
        reconcile_dsh(tmp_path, packages, catalog, targets=(Target.DSH, Target.CODEX))
    targets = (Target.CODEX,)
    reconcile_dsh(tmp_path, packages, catalog, targets=targets, include_catalog=False)
    inventory = read_dsh_inventory(project_layout(tmp_path))
    assert inventory.records == inventory.source_records == inventory.rule_blocks == {}
    assert not inventory.shared_rule_records
    assert name in agents_md.iter_rule_block_names((tmp_path / "AGENTS.md").read_text())
    assert not reconcile_dsh(
        tmp_path,
        packages,
        catalog,
        targets=targets,
        include_catalog=False,
        check_only=True,
    ).drift
    if local:
        _json(tmp_path / ".codex/.ai-dotfiles-local.json", {"rule_blocks": {}})
    assert agents_md.remove_rule_blocks(tmp_path / "AGENTS.md", {name})
    assert (tmp_path / "AGENTS.md").read_bytes() == b"User bytes  \r\n"
    assert not reconcile_dsh(
        tmp_path, [], catalog, targets=(), include_catalog=False, check_only=True
    ).drift


def test_independent_catalog_owner_conflict_refuses_before_refresh(
    tmp_path: Path, tmp_storage: Path
) -> None:
    catalog = tmp_storage / "catalog"
    _rule(tmp_path)
    migrate_to_dsh(tmp_path)
    _write(
        catalog / "bundle/rules/local.md", "---\nalways_on: true\n---\nOriginal body\n"
    )
    _rule(tmp_path, "Changed local body\n")
    before = _snapshot(tmp_path)
    with pytest.raises(ElementError, match="Conflicting shared target union"):
        reconcile_dsh(
            tmp_path,
            ["@bundle"],
            catalog,
            targets=(Target.CODEX,),
            include_catalog=False,
        )
    assert _snapshot(tmp_path) == before


def test_protected_catalog_original_change_after_plan_refuses_deletion(
    tmp_path: Path, tmp_storage: Path
) -> None:
    catalog = tmp_storage / "catalog"
    source = _write(
        catalog / "rules/shared.md", "---\nalways_on: true\n---\nShared body\n"
    )
    reconcile_dsh(tmp_path, ["rule:shared"], catalog)
    plan = plan_dsh_reconciliation(
        project_layout(tmp_path),
        ["rule:shared"],
        catalog,
        targets=(Target.CODEX,),
        include_catalog=False,
    )
    source.write_text("---\nalways_on: true\n---\nChanged\n")
    before = _snapshot(tmp_path)
    with pytest.raises(LinkError, match="Protected shared source changed"):
        prune_dsh(plan)
    assert _snapshot(tmp_path) == before


def test_global_prune_never_scans_home_or_adopts_unrecorded_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = tmp_path / "catalog"
    _skill(catalog)
    home = tmp_path / "disposable-home"
    _write(home / "unrelated/deep/sentinel", "Home sentinel\n")
    dsh_home = home / ".dsh"
    _write(dsh_home / "profiles/default/cordis.yml", "Native profile\n")
    _write(dsh_home / "cordis.patch.yml", "Native home patch\n")
    reconcile_dsh_global(["skill:sample"], catalog, configured_home=dsh_home)
    foreign = _write(dsh_home / "skills/foreign/SKILL.md", "User skill\n")
    before = _snapshot(home)
    with monkeypatch.context() as patch:

        def refuse_scan(*args: object, **kwargs: object) -> None:
            raise AssertionError("Global lifecycle must not recursively scan home")

        patch.setattr(Path, "rglob", refuse_scan)
        plan = plan_dsh_reconciliation(global_layout(dsh_home), [], catalog)
        assert prune_dsh(plan, check_only=True).exit_code == 1
        assert prune_dsh(plan).changed_paths
    after = _snapshot(home)
    for key, value in before.items():
        if key.startswith(".dsh/ai-dotfiles/") or key == ".dsh/skills/sample":
            continue
        if key in (".dsh/ai-dotfiles", ".dsh/skills"):
            continue
        assert after[key] == value
    assert foreign.exists()
    assert not reconcile_dsh_global(
        [], catalog, configured_home=dsh_home, check_only=True
    ).drift


@pytest.mark.parametrize("scope", ["project", "global"])
def test_unsafe_recorded_block_path_refuses_before_writes(
    tmp_path: Path, scope: str
) -> None:
    catalog = tmp_path / "catalog"
    _skill(catalog)
    layout = (
        project_layout(tmp_path)
        if scope == "project"
        else global_layout(tmp_path / "home")
    )
    prune_dsh(plan_dsh_reconciliation(layout, ["skill:sample"], catalog))
    data = json.loads(layout.provenance_path.read_bytes())
    data["rule_blocks"] = {"../AGENTS.md": ["foreign"]}
    _json(layout.provenance_path, data)
    before = _snapshot(tmp_path)
    with pytest.raises(ConfigError, match="Unsafe DSH rule block record"):
        plan_dsh_reconciliation(layout, [], catalog)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("mode", ["link", "copy"])
def test_gitignore_has_exact_verified_links_preserves_user_lines(
    tmp_path: Path, tmp_storage: Path, mode: str
) -> None:
    catalog = tmp_storage / "catalog"
    _skill(catalog)
    _write(catalog / "rules/shared.md", "---\nalways_on: true\n---\nShared\n")
    reconcile_dsh(tmp_path, ["skill:sample", "rule:shared"], catalog, mode=mode)
    foreign = tmp_path / ".dsh/skills/foreign"
    foreign.symlink_to(catalog / "skills/sample", target_is_directory=True)
    _write(tmp_path / ".gitignore", "# User lines\n.env\n")
    paths = collect_dsh_managed_paths(tmp_path)
    assert paths == (["/.dsh/skills/sample"] if mode == "link" else [])
    sync_gitignore(tmp_path, paths)
    data = (tmp_path / ".gitignore").read_text()
    assert data.startswith("# User lines\n.env\n")
    assert "AGENTS.md" not in data and "foreign" not in data
    reconcile_dsh(tmp_path, [], catalog)
    sync_gitignore(tmp_path, collect_dsh_managed_paths(tmp_path))
    assert (tmp_path / ".gitignore").read_text() == "# User lines\n.env\n"
    assert foreign.is_symlink()


def test_gitignore_refuses_modified_recorded_link(
    tmp_path: Path, tmp_storage: Path
) -> None:
    catalog = tmp_storage / "catalog"
    _skill(catalog)
    reconcile_dsh(tmp_path, ["skill:sample"], catalog)
    link = tmp_path / ".dsh/skills/sample"
    link.unlink()
    link.symlink_to(tmp_path / "absent")
    before = _snapshot(tmp_path)
    with pytest.raises(LinkError):
        collect_dsh_managed_paths(tmp_path)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("origin", ["catalog", "local"])
@pytest.mark.parametrize("kind", ["skill", "shared", "literal"])
def test_raw_crlf_sources_check_refresh_and_retire_without_false_drift(
    tmp_path: Path, tmp_storage: Path, origin: str, kind: str
) -> None:
    catalog = tmp_storage / "catalog"
    source_root = catalog if origin == "catalog" else tmp_path / ".claude"
    source = (
        source_root / "skills/sample/SKILL.md"
        if kind == "skill"
        else source_root / "rules/sample.md"
    )
    header = (
        "name: sample\ndescription: Sample\n"
        if kind == "skill"
        else "always_on: true\n" if kind == "shared" else "description: Literal\n"
    )
    raw = f"---\n{header}---\n\nFirst line  \nSecond {{{{literal}}}}\n".replace(
        "\n", "\r\n"
    )
    _write(source, raw)
    _write(tmp_path / "AGENTS.md", "User lines  \r\n")
    packages = (
        ["skill:sample" if kind == "skill" else "rule:sample"]
        if origin == "catalog"
        else []
    )
    if origin == "local":
        migrate_to_dsh(tmp_path)
    else:
        reconcile_dsh(tmp_path, packages, catalog)
    inventory = read_dsh_inventory(project_layout(tmp_path))
    record = next(iter(inventory.source_records.values()))
    assert record["source_text"] == raw
    assert (
        record["provenance"]["source_sha256"]
        == hashlib.sha256(raw.encode()).hexdigest()
    )
    if kind == "literal":
        assert record["body"] == "\r\nFirst line  \r\nSecond {{literal}}\r\n"
    before = _snapshot(tmp_path)
    assert reconcile_dsh(tmp_path, packages, catalog, check_only=True).exit_code == 0
    assert _snapshot(tmp_path) == before
    _write(source, raw.replace("Second", "Changed"))
    before = _snapshot(tmp_path)
    assert reconcile_dsh(tmp_path, packages, catalog, check_only=True).exit_code == 1
    assert _snapshot(tmp_path) == before
    reconcile_dsh(tmp_path, packages, catalog)
    assert not reconcile_dsh(tmp_path, packages, catalog, check_only=True).drift
    if kind == "shared":
        assert (
            b"First line  \r\nChanged {{literal}}"
            in (tmp_path / "AGENTS.md").read_bytes()
        )
        if origin == "local":
            _write(source, raw.replace("always_on: true", "description: Literal"))
            migrate_to_dsh(tmp_path)
            assert reconcile_dsh(tmp_path, packages, catalog).drift
    if origin == "local":
        if kind == "skill":
            shutil.rmtree(source.parent)
        else:
            source.unlink()
    reconcile_dsh(tmp_path, [], catalog)
    assert not read_dsh_inventory(project_layout(tmp_path)).shared_rule_records
    assert not reconcile_dsh(tmp_path, [], catalog, check_only=True).drift
    assert (tmp_path / "AGENTS.md").read_bytes() == b"User lines  \r\n"


@pytest.mark.parametrize(
    "mutation", ["schema", "generator", "source", "body", "identity"]
)
def test_historical_custody_shape_refuses_before_retirement(
    tmp_path: Path, tmp_storage: Path, mutation: str
) -> None:
    _rule(tmp_path)
    migrate_to_dsh(tmp_path)
    path = tmp_path / ".dsh/ai-dotfiles/provenance.json"
    data = json.loads(path.read_bytes())
    key, historical = next(iter(data["shared_rule_records"].items()))
    if mutation in ("schema", "generator"):
        historical["schema_version" if mutation == "schema" else "generator"] = 999
    elif mutation == "source":
        historical["source_record"]["source_text"] += "Tampered"
    elif mutation == "body":
        historical["source_record"]["body"] = "Tampered"
    else:
        data["shared_rule_records"]["f" * 64] = data["shared_rule_records"].pop(key)
    _json(path, data)
    (tmp_path / ".claude/rules/local.md").unlink()
    before = _snapshot(tmp_path)
    with pytest.raises(ConfigError, match="historical.*custody"):
        reconcile_dsh(tmp_path, [], tmp_storage / "catalog")
    assert _snapshot(tmp_path) == before


def test_recomputed_marker_sha_cannot_prove_historical_body(
    tmp_path: Path, tmp_storage: Path
) -> None:
    rule = _rule(tmp_path)
    migrate_to_dsh(tmp_path)
    path = tmp_path / "AGENTS.md"
    data = path.read_text().replace("Original body", "Foreign body")
    old = hashlib.sha256(b"Original body").hexdigest()
    new = hashlib.sha256(b"Foreign body").hexdigest()
    _write(path, data.replace(old, new))
    rule.unlink()
    before = _snapshot(tmp_path)
    with pytest.raises(LinkError, match="body"):
        reconcile_dsh(tmp_path, [], tmp_storage / "catalog")
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("intermediate", ["manual", "literal"])
def test_historical_custody_allows_return_to_shared_and_refresh(
    tmp_path: Path, tmp_storage: Path, intermediate: str
) -> None:
    rule = _rule(tmp_path)
    migrate_to_dsh(tmp_path)
    _write(
        rule,
        "---\n"
        + ("paths: [src]\n" if intermediate == "manual" else "description: Literal\n")
        + "---\nIntermediate\n",
    )
    migrate_to_dsh(tmp_path)
    _rule(tmp_path, "Final shared body\n")
    catalog = tmp_storage / "catalog"
    assert reconcile_dsh(tmp_path, [], catalog, check_only=True).exit_code == 1
    reconcile_dsh(tmp_path, [], catalog)
    assert b"Final shared body" in (tmp_path / "AGENTS.md").read_bytes()
    assert b"Original body" not in (tmp_path / "AGENTS.md").read_bytes()
    historical = next(
        iter(read_dsh_inventory(project_layout(tmp_path)).shared_rule_records.values())
    )
    assert historical["source_record"]["body"] == "Final shared body"
    assert not reconcile_dsh(tmp_path, [], catalog, check_only=True).drift


def _typed_inputs(
    root: Path, catalog: Path, packages: list[str], mode: str = "link"
) -> DshLocalInputs:
    assert mode in ("link", "copy")
    return collect_dsh_local_inputs(
        root,
        manifest_packages=packages,
        catalog_plan=collect_dsh_elements(
            parse_elements(packages), project_layout(root), catalog, mode=mode
        ),
        mode=mode,
    )


@pytest.mark.parametrize("mode", ["link", "copy"])
def test_precomputed_full_local_inputs_match_default_one_composition(
    tmp_path: Path, tmp_storage: Path, mode: str
) -> None:
    catalog = tmp_storage / "catalog"
    _skill(catalog / "bundle", "catalogued")
    _json(
        catalog / "bundle/settings.fragment.json",
        {"env": {"CATALOG_VALUE": "catalog"}, "permissions": {"deny": ["Read"]}},
    )
    _skill(tmp_path / ".claude", "local-skill")
    _rule(tmp_path)
    _json(
        tmp_path / ".claude/settings.local.json",
        {"env": {"LOCAL_VALUE": "local"}, "permissions": {"deny": ["Bash"]}},
    )
    migrate_to_dsh(tmp_path, mode=mode)
    packages = ["@bundle"]
    inputs = _typed_inputs(tmp_path, catalog, packages, mode)
    before = _snapshot(tmp_path)
    default = plan_dsh_reconciliation(
        project_layout(tmp_path), packages, catalog, mode=mode
    )
    supplied = plan_dsh_reconciliation(
        project_layout(tmp_path), packages, catalog, mode=mode, local_inputs=inputs
    )
    assert supplied == default
    assert supplied.migration is not None
    assert supplied.migration.inputs.install is inputs.install
    assert supplied.migration.config.environment == {
        "CATALOG_VALUE": "catalog",
        "LOCAL_VALUE": "local",
    }
    assert supplied.migration.config.permissions.deny == ("bash", "read", "read_image")
    assert len(supplied.migration.config.permissions.contributions) == 2
    check = reconcile_dsh(
        tmp_path, packages, catalog, mode=mode, local_inputs=inputs, check_only=True
    )
    assert check.exit_code == 1 and not check.changed_paths
    assert _snapshot(tmp_path) == before
    assert reconcile_dsh(
        tmp_path, packages, catalog, mode=mode, local_inputs=inputs
    ).changed_paths
    assert not reconcile_dsh(
        tmp_path,
        packages,
        catalog,
        mode=mode,
        local_inputs=_typed_inputs(tmp_path, catalog, packages, mode),
        check_only=True,
    ).drift
    assert not reconcile_dsh(
        tmp_path, packages, catalog, mode=mode, check_only=True
    ).drift


@pytest.mark.parametrize("check_only", [False, True])
@pytest.mark.parametrize("phase", ["before-plan", "before-apply"])
@pytest.mark.parametrize("mutation", ["local", "catalog", "raw", "ledger"])
def test_supplied_local_inputs_refuse_stale_originals_without_writes(
    tmp_path: Path,
    tmp_storage: Path,
    mutation: str,
    phase: str,
    check_only: bool,
) -> None:
    catalog = tmp_storage / "catalog"
    catalog_source = _skill(catalog)
    local = _rule(tmp_path)
    raw = _json(tmp_path / ".claude/settings.local.json", {})
    migrate_to_dsh(tmp_path)
    inputs = _typed_inputs(tmp_path, catalog, ["skill:sample"])
    plan = (
        plan_dsh_reconciliation(
            project_layout(tmp_path), ["skill:sample"], catalog, local_inputs=inputs
        )
        if phase == "before-apply"
        else None
    )
    source = {
        "local": local,
        "catalog": catalog_source,
        "raw": raw,
        "ledger": tmp_path / ".claude/.ai-dotfiles-copies.json",
    }[mutation]
    _write(source, source.read_bytes().decode() + "\n" if source.exists() else "{}")
    before = _snapshot(tmp_path)
    with pytest.raises((ConfigError, LinkError), match="changed|disagree"):
        if plan is not None:
            apply_dsh_reconciliation(plan, check_only=check_only)
        else:
            reconcile_dsh(
                tmp_path,
                ["skill:sample"],
                catalog,
                local_inputs=inputs,
                check_only=check_only,
            )
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("mismatch", ["project", "install", "global"])
def test_supplied_inputs_require_one_project_layout_before_writes(
    tmp_path: Path, tmp_storage: Path, mismatch: str
) -> None:
    _rule(tmp_path)
    catalog = tmp_storage / "catalog"
    inputs = _typed_inputs(tmp_path, catalog, [])
    layout = project_layout(tmp_path)
    other = project_layout(tmp_path / "other")
    if mismatch == "project":
        inputs = replace(inputs, layout=other)
    elif mismatch == "install":
        inputs = replace(inputs, install=replace(inputs.install, layout=other))
    else:
        layout = global_layout(tmp_path / "global")
    before = _snapshot(tmp_path)
    with pytest.raises(ConfigError, match="matching project layout"):
        plan_dsh_reconciliation(layout, [], catalog, local_inputs=inputs)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "mismatch",
    ["selection", "disabled", "mode", "resources", "outputs", "instructions"],
)
def test_supplied_inputs_require_matching_fresh_catalog_before_writes(
    tmp_path: Path, tmp_storage: Path, mismatch: str
) -> None:
    catalog = tmp_storage / "catalog"
    _skill(catalog / "bundle", "catalogued")
    _rule(tmp_path)
    inputs = _typed_inputs(tmp_path, catalog, ["@bundle"])
    if mismatch == "resources":
        inputs = replace(inputs, install=replace(inputs.install, resources=()))
    elif mismatch == "outputs":
        inputs = replace(inputs, install=replace(inputs.install, outputs=()))
    elif mismatch == "instructions":
        inputs = replace(inputs, install=replace(inputs.install, instructions=None))
    before = _snapshot(tmp_path)
    with pytest.raises(ConfigError, match="disagree.*fresh catalog"):
        plan_dsh_reconciliation(
            project_layout(tmp_path),
            [] if mismatch == "selection" else ["@bundle"],
            catalog,
            include_catalog=mismatch != "disabled",
            mode="copy" if mismatch == "mode" else "link",
            local_inputs=inputs,
        )
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("check_only", [False, True])
def test_supplied_inputs_keep_registry_guard_before_consumption(
    tmp_path: Path, tmp_storage: Path, check_only: bool
) -> None:
    _rule(tmp_path)
    migrate_to_dsh(tmp_path)
    catalog = tmp_storage / "catalog"
    plan = plan_dsh_reconciliation(
        project_layout(tmp_path),
        [],
        catalog,
        local_inputs=_typed_inputs(tmp_path, catalog, []),
    )
    path = tmp_path / ".dsh/ai-dotfiles/local.json"
    path.write_bytes(path.read_bytes() + b"\n")
    before = _snapshot(tmp_path)
    with pytest.raises(LinkError, match="registry changed"):
        apply_dsh_reconciliation(plan, check_only=check_only)
    assert _snapshot(tmp_path) == before

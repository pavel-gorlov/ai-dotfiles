"""Catalog lifecycle contracts for DSH and shared Claude/Codex ownership."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.cli import cli
from ai_dotfiles.core import agents_md, manifest
from ai_dotfiles.core.dsh_install import read_dsh_inventory
from ai_dotfiles.core.dsh_layout import global_layout, project_layout
from ai_dotfiles.core.dsh_local_registry import load_dsh_local_registry
from ai_dotfiles.core.dsh_migrate import (
    collect_dsh_local_inputs,
    migrate_to_dsh,
    plan_dsh_catalog_lifecycle,
    verify_dsh_local_inputs,
)
from ai_dotfiles.core.dsh_reconcile import (
    apply_dsh_reconciliation,
    reconcile_dsh,
)
from ai_dotfiles.core.errors import LinkError
from ai_dotfiles.core.settings_ownership import save_settings_ownership
from ai_dotfiles.core.targets import Target
from tests.integration.test_dsh_reconcile import _snapshot


@pytest.fixture(autouse=True)
def isolated_homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every CLI case uses disposable user, DSH, Codex and catalog roots."""
    home = tmp_path / "home"
    home.mkdir()
    storage = tmp_path / "storage"
    (storage / "catalog").mkdir(parents=True)
    (storage / "global").mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("DSH_HOME", str(home / "dsh"))
    monkeypatch.setenv("CODEX_HOME", str(home / "codex"))
    monkeypatch.setenv("AI_DOTFILES_HOME", str(storage))


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    return path


def _json(path: Path, value: object) -> Path:
    return _write(path, json.dumps(value))


def _skill(root: Path, name: str) -> Path:
    return _write(
        root / "skills" / name / "SKILL.md",
        f"---\nname: {name}\ndescription: Skill {name}\n---\n{name} body\n",
    )


def _domain(catalog: Path, name: str) -> None:
    root = catalog / name
    _skill(root, name)
    _write(
        root / "agents" / f"{name}-agent.md",
        f"---\nname: {name}-agent\ndescription: {name} child\n"
        "model: inherit\n---\nLiteral {{parent}} body\n",
    )
    _write(root / "rules" / f"{name}-rule.md", "---\nalways_on: true\n---\nBody\n")
    _json(
        root / "settings.fragment.json",
        {"env": {name.upper(): name}, "permissions": {"deny": ["Read"]}},
    )
    _json(
        root / "mcp.fragment.json",
        {"mcpServers": {name: {"command": "node", "args": ["fake.mjs"]}}},
    )
    _write(root / "fake.mjs", "process.exit(0);\n")


def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / ".git").mkdir()
    monkeypatch.chdir(root)
    return root


def _manifest(
    root: Path, packages: list[str], targets: list[str] | None, mode: str = "symlink"
) -> Path:
    value: dict[str, object] = {"packages": packages, "link_mode": mode}
    if targets is not None:
        value["targets"] = targets
    return _json(root / "ai-dotfiles.json", value)


def _invoke(*args: str) -> None:
    result = CliRunner().invoke(cli, list(args))
    assert result.exit_code == 0, (result.output, result.exception)


def _catalog_check(
    root: Path | None, packages: list[str], catalog: Path, targets: list[str], mode: str
) -> None:
    plan = plan_dsh_catalog_lifecycle(
        root, packages, catalog, targets, mode="copy" if mode == "copy" else "link"
    )
    assert plan is not None
    before = _snapshot(root or global_layout().dsh_dir)
    report = apply_dsh_reconciliation(plan, check_only=True)
    assert report.exit_code == 0, report.drift
    assert _snapshot(root or global_layout().dsh_dir) == before


@pytest.mark.parametrize("scope", ["project", "global"])
@pytest.mark.parametrize("targets", [["dsh"], ["claude", "codex", "dsh"]])
@pytest.mark.parametrize("mode", ["symlink", "copy"])
def test_catalog_install_add_remove_both_scopes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
    targets: list[str],
    mode: str,
) -> None:
    catalog = tmp_path / "storage/catalog"
    _domain(catalog, "alpha")
    _domain(catalog, "beta")
    root = _project(tmp_path, monkeypatch)
    is_global = scope == "global"
    if is_global:
        _json(
            tmp_path / "storage/global.json",
            {"packages": ["@alpha"], "targets": targets},
        )
        layout = global_layout()
        args = ("-g",)
    else:
        _manifest(root, ["@alpha"], targets, mode)
        layout = project_layout(root)
        args = ()
    _write(layout.root_agents_md, "User instructions  \r\n")
    foreign = _write(layout.skills_dir / "foreign/SKILL.md", "User skill\n")
    profile = _write(layout.dsh_dir / "profiles/user/cordis.yml", "User profile\n")
    _invoke("install", *args)
    assert (layout.skills_dir / "alpha").is_symlink() == (
        is_global or mode == "symlink"
    )
    assert "alpha-rule" in agents_md.iter_rule_block_names(
        layout.root_agents_md.read_text()
    )
    config = json.loads(layout.config_path.read_bytes())
    assert config["environment"] == {"ALPHA": "alpha"}
    _invoke("install", *args, "--prune")
    _catalog_check(
        None if is_global else root,
        ["@alpha"],
        catalog,
        targets,
        "symlink" if is_global else mode,
    )
    _invoke("add", *args, "@beta")
    config = json.loads(layout.config_path.read_bytes())
    assert config["environment"] == {"ALPHA": "alpha", "BETA": "beta"}
    names = {part["name"] for part in config["contributions"]}
    assert {"mcp:alpha", "mcp:beta"} <= names
    _invoke("remove", *args, "@alpha")
    assert not (layout.skills_dir / "alpha").exists()
    assert (layout.skills_dir / "beta/SKILL.md").is_file()
    assert json.loads(layout.config_path.read_bytes())["environment"] == {
        "BETA": "beta"
    }
    _invoke("remove", *args, "@beta")
    assert read_dsh_inventory(layout).records == {}
    assert layout.root_agents_md.read_bytes() == b"User instructions  \r\n"
    assert foreign.read_bytes() == b"User skill\n"
    assert profile.read_bytes() == b"User profile\n"
    _invoke("install", *args, "--prune")
    _catalog_check(
        None if is_global else root,
        [],
        catalog,
        targets,
        "symlink" if is_global else mode,
    )


@pytest.mark.parametrize("mode", ["symlink", "copy"])
def test_all_target_changed_shared_rule_repeated_install_is_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    root = _project(tmp_path, monkeypatch)
    catalog = tmp_path / "storage/catalog"
    _domain(catalog, "alpha")
    targets = ["claude", "codex", "dsh"]
    _manifest(root, ["@alpha"], targets, mode)
    _invoke("install")
    rule = catalog / "alpha/rules/alpha-rule.md"
    _write(rule, "---\nalways_on: true\n---\nChanged body\n")
    _invoke("install", "--prune")
    text = (root / "AGENTS.md").read_text()
    assert text.count("Changed body") == 1
    assert text.count("ai-dotfiles:rule:alpha-rule START") == 1
    assert not reconcile_dsh(
        root,
        ["@alpha"],
        catalog,
        targets=(Target.CLAUDE, Target.CODEX, Target.DSH),
        mode="copy" if mode == "copy" else "link",
        check_only=True,
    ).drift
    _invoke("install")
    _catalog_check(root, ["@alpha"], catalog, targets, mode)


@pytest.mark.parametrize(
    "relative",
    [
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".claude/hooks.json",
        ".mcp.json",
    ],
)
def test_unregistered_json_and_colliding_command_stay_inactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: str
) -> None:
    root = _project(tmp_path, monkeypatch)
    catalog = tmp_path / "storage/catalog"
    _skill(root / ".claude", "registered")
    migrate_to_dsh(root)
    original_keys = set(load_dsh_local_registry(root).sources)
    value: object = (
        {"mcpServers": {"unregistered": {"command": "node"}}}
        if relative == ".mcp.json"
        else {"permissions": {"deny": ["Bash"]}} if "settings" in relative else {}
    )
    _json(root / relative, value)
    _skill(root / ".claude", "unregistered")
    _write(
        root / ".claude/commands/unregistered.md",
        "---\nname: registered\ndescription: New command\n"
        "disable-model-invocation: true\n---\nUnregistered\n",
    )
    _skill(catalog, "sample")
    _manifest(root, ["skill:sample"], ["dsh"])
    _invoke("install", "--prune")
    assert set(load_dsh_local_registry(root).sources) == original_keys
    assert not (root / ".dsh/skills/unregistered").exists()
    snapshot = json.loads(project_layout(root).config_path.read_bytes())
    assert all(
        source["source"] != str(root / relative) for source in snapshot["sources"]
    )
    assert not any(
        part["name"] == "mcp:unregistered" for part in snapshot["contributions"]
    )
    _catalog_check(root, ["skill:sample"], catalog, ["dsh"], "symlink")
    _invoke("remove", "skill:sample")
    assert (root / ".dsh/skills/registered/SKILL.md").is_file()
    assert set(load_dsh_local_registry(root).sources) == original_keys


@pytest.mark.parametrize("change", ["modify", "delete"])
def test_registered_local_skill_refresh_and_retirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    root = _project(tmp_path, monkeypatch)
    source = _skill(root / ".claude", "registered")
    migrate_to_dsh(root)
    _manifest(root, [], ["dsh"])
    if change == "modify":
        _write(
            source, source.read_text().replace("registered body", "Fresh local body")
        )
    else:
        shutil.rmtree(source.parent)
    _invoke("install", "--prune")
    target = root / ".dsh/skills/registered/SKILL.md"
    if change == "modify":
        assert "Fresh local body" in target.read_text()
    else:
        assert not target.exists()
        assert not load_dsh_local_registry(root).sources


@pytest.mark.parametrize("change", ["bytes", "remove"])
def test_registered_selection_guards_original_registry_until_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    root = _project(tmp_path, monkeypatch)
    _skill(root / ".claude", "registered")
    migrate_to_dsh(root)
    layout = project_layout(root)
    inputs = collect_dsh_local_inputs(root, registered_only=True)
    if change == "bytes":
        layout.local_registry_path.write_bytes(
            layout.local_registry_path.read_bytes() + b" "
        )
    else:
        layout.local_registry_path.unlink()
    before = _snapshot(root)
    with pytest.raises(LinkError, match="original/ownership changed"):
        verify_dsh_local_inputs(inputs)
    assert _snapshot(root) == before


@pytest.mark.parametrize(
    "relative",
    [
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".claude/hooks.json",
        ".mcp.json",
    ],
)
def test_selected_inputs_guard_complete_observed_json_presence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: str
) -> None:
    root = _project(tmp_path, monkeypatch)
    _skill(root / ".claude", "registered")
    migrate_to_dsh(root)
    _json(root / relative, {})
    inputs = collect_dsh_local_inputs(root, registered_only=True)
    assert not inputs.raw_sources
    assert len(inputs.observed_raw_sources or ()) == 1
    (root / relative).unlink()
    with pytest.raises(LinkError):
        verify_dsh_local_inputs(inputs)


def test_registry_created_after_empty_registered_selection_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, monkeypatch)
    inputs = collect_dsh_local_inputs(root, registered_only=True)
    _skill(root / ".claude", "registered")
    migrate_to_dsh(root)
    with pytest.raises(LinkError, match="original/ownership changed"):
        verify_dsh_local_inputs(inputs)


def test_full_migration_default_still_discovers_new_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, monkeypatch)
    _skill(root / ".claude", "registered")
    migrate_to_dsh(root)
    _skill(root / ".claude", "new")
    assert (
        ".claude/skills/new/SKILL.md"
        in collect_dsh_local_inputs(root).current_source_keys
    )
    assert (
        ".claude/skills/new/SKILL.md"
        not in collect_dsh_local_inputs(root, registered_only=True).current_source_keys
    )


def test_fresh_registered_originals_never_activate_registry_value_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, monkeypatch)
    source = _json(
        root / ".claude/settings.local.json", {"permissions": {"deny": ["Read"]}}
    )
    migrate_to_dsh(root)
    _json(source, {"permissions": {"deny": ["Bash"]}})
    _manifest(root, [], ["dsh"])
    _invoke("install")
    data = json.loads(project_layout(root).config_path.read_bytes())
    assert data["permissions"]["deny"] == ["bash"]
    registry = load_dsh_local_registry(root)
    assert registry.sources[".claude/settings.local.json"]["value"] == {
        "permissions": {"deny": ["Bash"]}
    }


def test_unproven_owned_environment_refuses_without_snapshot_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, monkeypatch)
    _json(
        root / ".claude/settings.json",
        {"permissions": {"deny": ["Read"]}, "env": {"LOCAL_SENTINEL": "original"}},
    )
    migrate_to_dsh(root)
    save_settings_ownership(root / ".claude", {"permissions_deny": []})
    _manifest(root, [], ["dsh"])
    before = _snapshot(root)
    result = CliRunner().invoke(cli, ["install"])
    assert result.exit_code != 0
    assert "local .claude/settings.json env:" in result.output
    assert "no provable original local-user origin" in result.output
    assert _snapshot(root) == before


@pytest.mark.parametrize("targets", [["codex"], ["claude", "codex", "dsh"]])
def test_codex_prune_keeps_both_local_registries_with_empty_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, targets: list[str]
) -> None:
    root = _project(tmp_path, monkeypatch)
    local = _write(
        root / ".claude/rules/local.md", "---\nalways_on: true\n---\nLocal\n"
    )
    migrate_to_dsh(root)
    from ai_dotfiles.core.codex_local_registry import save_local_registry

    agents_md.upsert_rule_block(root / "AGENTS.md", "codex-source", "Codex local\n")
    save_local_registry(
        root,
        {"skills": {}, "agents": {}, "rule_blocks": {"AGENTS.md": ["codex-source"]}},
    )
    _manifest(root, [], targets)
    _invoke("install", "--prune")
    text = (root / "AGENTS.md").read_text()
    assert {"local", "codex-source"} <= set(agents_md.iter_rule_block_names(text))
    assert local.exists()
    assert project_layout(root).local_registry_path.exists()


def test_remove_codex_catalog_keeps_independent_local_rule_custody(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, monkeypatch)
    local = _write(
        root / ".claude/rules/shared.md", "---\nalways_on: true\n---\nSame\n"
    )
    migrate_to_dsh(root)
    catalog = tmp_path / "storage/catalog"
    _write(catalog / "rules/shared.md", local.read_text())
    _manifest(root, ["rule:shared"], ["codex"])
    _invoke("install")
    _invoke("remove", "rule:shared")
    assert "shared" in agents_md.iter_rule_block_names((root / "AGENTS.md").read_text())
    assert load_dsh_local_registry(root).sources


@pytest.mark.parametrize("disabled", [False, True])
def test_empty_disabled_target_retains_user_and_registered_locals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, disabled: bool
) -> None:
    root = _project(tmp_path, monkeypatch)
    _skill(root / ".claude", "local")
    migrate_to_dsh(root)
    catalog = tmp_path / "storage/catalog"
    _skill(catalog, "sample")
    path = _manifest(root, ["skill:sample"], ["dsh"])
    _invoke("install")
    if disabled:
        _json(path, {"packages": ["skill:sample"], "targets": ["codex"]})
    else:
        _json(path, {"packages": [], "targets": ["dsh"]})
    _invoke("install", "--prune")
    assert not (root / ".dsh/skills/sample").exists()
    assert (root / ".dsh/skills/local/SKILL.md").is_file()
    assert ".claude/skills/local/SKILL.md" in load_dsh_local_registry(root).sources


@pytest.mark.parametrize("scope", ["project", "global"])
def test_foreign_collision_refuses_before_target_files_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str
) -> None:
    root = _project(tmp_path, monkeypatch)
    catalog = tmp_path / "storage/catalog"
    _skill(catalog, "sample")
    targets = ["claude", "codex", "dsh"]
    if scope == "global":
        _json(
            tmp_path / "storage/global.json",
            {"packages": ["skill:sample"], "targets": targets},
        )
        layout = global_layout()
        args = ["install", "-g"]
    else:
        _manifest(root, ["skill:sample"], targets)
        layout = project_layout(root)
        args = ["install"]
    _write(layout.skills_dir / "sample/SKILL.md", "Foreign user bytes\n")
    before = _snapshot(tmp_path)
    result = CliRunner().invoke(cli, args)
    assert result.exit_code != 0
    assert "refusing" in result.output.lower()
    # Claude directories may be initialized, but no user/catalog outputs change.
    after = _snapshot(tmp_path)
    assert all(after.get(key) == value for key, value in before.items() if value[2])
    assert not (root / ".agents/skills/sample").exists()
    assert not (root / ".claude/skills/sample").exists()


@pytest.mark.parametrize("mode", ["symlink", "copy"])
@pytest.mark.parametrize("optout", ["none", "flag", "manifest", "global"])
def test_gitignore_lists_only_exact_managed_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, optout: str
) -> None:
    root = _project(tmp_path, monkeypatch)
    catalog = tmp_path / "storage/catalog"
    _skill(catalog, "sample")
    _manifest(root, ["skill:sample"], ["dsh"], mode)
    _write(root / "AGENTS.md", "User\n")
    if optout == "manifest":
        value = manifest.read_manifest(root / "ai-dotfiles.json")
        value["manage_gitignore"] = False
        _json(root / "ai-dotfiles.json", value)
    if optout == "global":
        _json(
            tmp_path / "storage/global.json",
            {"packages": [], "manage_gitignore": False},
        )
    _invoke("install", *("--no-gitignore",) if optout == "flag" else ())
    gitignore = root / ".gitignore"
    if optout != "none":
        assert not gitignore.exists()
    else:
        text = gitignore.read_text() if gitignore.exists() else ""
        assert ("/.dsh/skills/sample" in text) == (mode == "symlink")
        assert "AGENTS.md" not in text
        assert "/.dsh/" not in text.splitlines()


@pytest.mark.parametrize("targets", [None, [], ["unknown"]])
def test_default_empty_unknown_targets_do_not_activate_dsh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, targets: list[str] | None
) -> None:
    root = _project(tmp_path, monkeypatch)
    _skill(tmp_path / "storage/catalog", "sample")
    _manifest(root, ["skill:sample"], targets)
    _invoke("install", "--prune")
    assert not (root / ".dsh").exists()
    assert not global_layout().dsh_dir.exists()
    assert (root / ".claude/skills/sample").exists() == (targets is None)


@pytest.mark.parametrize("scope", ["project", "global"])
def test_strict_dependency_gate_then_auto_expansion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str
) -> None:
    root = _project(tmp_path, monkeypatch)
    catalog = tmp_path / "storage/catalog"
    _skill(catalog, "base")
    leaf = _skill(catalog, "leaf")
    _write(
        leaf,
        leaf.read_text().replace("description:", "depends: [skill:base]\ndescription:"),
    )
    if scope == "global":
        _json(
            tmp_path / "storage/global.json",
            {"packages": ["skill:leaf"], "targets": ["dsh"]},
        )
        args = ["install", "-g"]
        layout = global_layout()
    else:
        _manifest(root, ["skill:leaf"], ["dsh"])
        args = ["install"]
        layout = project_layout(root)
    result = CliRunner().invoke(cli, [*args, "--strict-deps"])
    assert result.exit_code != 0
    assert "transitive dependencies" in result.output
    assert not layout.provenance_path.exists()
    _invoke(*args)
    assert (layout.skills_dir / "base/SKILL.md").exists()
    assert (layout.skills_dir / "leaf/SKILL.md").exists()


@pytest.mark.parametrize("targets", [None, [], ["unknown"], ["claude"]])
@pytest.mark.parametrize("foreign", ["registry", "symlink"])
def test_disabled_dsh_ignores_foreign_or_redirected_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    targets: list[str] | None,
    foreign: str,
) -> None:
    root = _project(tmp_path, monkeypatch)
    _skill(tmp_path / "storage/catalog", "sample")
    _manifest(root, ["skill:sample"], targets)
    if foreign == "registry":
        _json(root / ".dsh/ai-dotfiles/provenance.json", {"foreign": "user data"})
        guarded = root / ".dsh"
    else:
        guarded = tmp_path / "foreign-dsh"
        guarded.mkdir()
        _write(guarded / "sentinel", "Original user bytes\n")
        (root / ".dsh").symlink_to(guarded, target_is_directory=True)
    before = _snapshot(guarded)
    _invoke("install", "--prune")
    _invoke("remove", "skill:sample")
    _invoke("add", "skill:sample")
    assert _snapshot(guarded) == before


def test_disabled_global_dsh_does_not_adopt_foreign_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project(tmp_path, monkeypatch)
    _skill(tmp_path / "storage/catalog", "sample")
    _json(tmp_path / "storage/global.json", {"packages": ["skill:sample"]})
    _json(global_layout().provenance_path, {"foreign": "user data"})
    before = _snapshot(global_layout().dsh_dir)
    _invoke("install", "-g", "--prune")
    _invoke("remove", "-g", "skill:sample")
    _invoke("add", "-g", "skill:sample")
    assert _snapshot(global_layout().dsh_dir) == before


@pytest.mark.parametrize("mutation", ["registry", "local", "observed_json"])
def test_selected_lifecycle_refuses_changed_inputs_before_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    root = _project(tmp_path, monkeypatch)
    source = _skill(root / ".claude", "registered")
    migrate_to_dsh(root)
    observed = _json(root / ".claude/settings.local.json", {})
    catalog = tmp_path / "storage/catalog"
    _skill(catalog, "sample")
    plan = plan_dsh_catalog_lifecycle(root, ["skill:sample"], catalog, ["dsh"])
    assert plan is not None
    if mutation == "registry":
        path = project_layout(root).local_registry_path
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "local":
        source.write_bytes(source.read_bytes() + b"Changed\n")
    else:
        _json(observed, {"permissions": {"deny": ["Bash"]}})
    before = _snapshot(root)
    with pytest.raises(LinkError):
        apply_dsh_reconciliation(plan)
    assert _snapshot(root) == before


@pytest.mark.parametrize("foreign", ["registry", "symlink"])
def test_selected_dsh_refuses_foreign_or_redirected_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    foreign: str,
) -> None:
    root = _project(tmp_path, monkeypatch)
    _skill(tmp_path / "storage/catalog", "sample")
    _manifest(root, ["skill:sample"], ["dsh"])
    if foreign == "registry":
        _json(root / ".dsh/ai-dotfiles/provenance.json", {"foreign": "user data"})
    else:
        destination = tmp_path / "foreign-dsh"
        destination.mkdir()
        (root / ".dsh").symlink_to(destination, target_is_directory=True)
    before = _snapshot(tmp_path)
    result = CliRunner().invoke(cli, ["install", "--prune"])
    assert result.exit_code != 0
    assert _snapshot(tmp_path) == before


def test_selected_json_projection_cannot_disagree_with_observed_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    root = _project(tmp_path, monkeypatch)
    _json(root / ".claude/settings.local.json", {"permissions": {"deny": ["Bash"]}})
    migrate_to_dsh(root)
    inputs = collect_dsh_local_inputs(root, registered_only=True)
    forged = replace(inputs.raw_sources[0], value={})
    before = _snapshot(root)
    with pytest.raises(LinkError, match="projection changed"):
        verify_dsh_local_inputs(replace(inputs, raw_sources=(forged,)))
    assert _snapshot(root) == before

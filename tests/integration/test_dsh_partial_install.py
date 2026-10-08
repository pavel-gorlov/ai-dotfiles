"""Partial static admission keeps original gaps and exact custody checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ai_dotfiles.core.dsh_install import (
    apply_dsh_install,
    collect_dsh_elements,
    read_dsh_inventory,
)
from ai_dotfiles.core.dsh_launch import _collect_plan, prepare_dsh_launch
from ai_dotfiles.core.dsh_layout import DshLayout, global_layout, project_layout
from ai_dotfiles.core.dsh_migrate import migrate_to_dsh
from ai_dotfiles.core.dsh_native import (
    DshNativeRuntime,
    native_frontmatter,
    resolve_dsh_runtime,
)
from ai_dotfiles.core.dsh_reconcile import (
    apply_dsh_reconciliation,
    plan_dsh_reconciliation,
)
from ai_dotfiles.core.elements import parse_elements
from ai_dotfiles.core.errors import ConfigError, LinkError
from ai_dotfiles.core.targets import Target
from tests.e2e.test_dsh_launch import _run
from tests.e2e.test_dsh_launch import managed_fixture as _managed_fixture

managed_fixture = _managed_fixture

pytestmark = pytest.mark.integration


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def skill(path: Path, name: str, *, bad: bool = False) -> Path:
    return write(
        path / "SKILL.md",
        f"---\nname: {name}\ndescription: Use {name}\n"
        + ("allowed-tools: Bash\n" if bad else "")
        + "---\nOriginal body.\n",
    )


def tree(path: Path) -> dict[str, bytes | str]:
    return {
        str(item.relative_to(path)): (
            str(item.readlink()) if item.is_symlink() else item.read_bytes()
        )
        for item in path.rglob("*")
        if item.is_symlink() or item.is_file()
    }


def settings() -> dict[str, object]:
    return {
        "permissions": {
            "deny": ["Write", "Bash(git commit:*)"],
            "ask": ["Edit"],
        },
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "echo rejected-guard",
                            "if": "Bash(git commit:*)",
                        },
                        {"type": "command", "command": "echo healthy-guard"},
                    ],
                }
            ]
        },
    }


@pytest.fixture
def catalog(tmp_storage: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "dsh-home"))
    result = tmp_storage / "catalog"
    write(result / "mixed/domain.json", '{"name":"mixed","description":"Mixed"}')
    write(result / "mixed/settings.fragment.json", json.dumps(settings()))
    skill(result / "mixed/skills/good", "good")
    skill(result / "mixed/skills/bad", "bad", bad=True)
    return result


def layout(tmp_path: Path, scope: str) -> DshLayout:
    if scope == "global":
        return global_layout(tmp_path / "dsh-home")
    root = tmp_path / "project"
    root.mkdir(exist_ok=True)
    return project_layout(root)


@pytest.mark.parametrize("scope", ["project", "global"])
def test_healthy_siblings_and_exact_policy_activate_with_original_gaps(
    catalog: Path, tmp_path: Path, scope: str
) -> None:
    target = layout(tmp_path, scope)
    original = tree(catalog)
    plan = plan_dsh_reconciliation(target, ["@mixed"], catalog)
    assert plan.partial and plan.skipped
    assert all(item.blocking for item in plan.skipped)
    report = apply_dsh_reconciliation(plan)
    assert report.partial
    assert (target.skills_dir / "good/SKILL.md").is_file()
    assert not (target.skills_dir / "bad").exists()
    hooks = json.loads(target.hooks_path.read_bytes())
    assert hooks["hooks"]["PreToolUse"] == [
        {
            "matcher": "bash",
            "hooks": [{"type": "command", "command": "echo healthy-guard"}],
        }
    ]
    assert any(item["blocking"] for item in hooks["aiDotfiles"]["diagnostics"])
    snapshot = json.loads(target.config_path.read_bytes())
    assert snapshot["permissions"]["blocked"] is True
    bridge = next(row for row in snapshot["rows"] if row["id"] == "ai-dotfiles-bridge")
    policy = bridge["config"]["permissions"]
    assert policy["deny"] == ["write"] and policy["ask"] == ["edit"]
    assert policy["requiredTools"] == ["edit", "write"] and policy["blocked"] is False
    assert "allow" not in policy
    assert {
        row["status"] for row in read_dsh_inventory(target).source_records.values()
    } == {"READY", "MANUAL"}
    assert tree(catalog) == original
    written = tree(target.dsh_dir)
    second = apply_dsh_reconciliation(
        plan_dsh_reconciliation(target, ["@mixed"], catalog)
    )
    assert second.changed_paths == () and second.drift == []
    assert tree(target.dsh_dir) == written


@pytest.mark.parametrize("scope", ["project", "global"])
def test_strict_refuses_entire_catalog_before_writes(
    catalog: Path, tmp_path: Path, scope: str
) -> None:
    target = layout(tmp_path, scope)
    original = tree(tmp_path)
    with pytest.raises(ConfigError):
        plan_dsh_reconciliation(target, ["@mixed"], catalog, strict=True)
    assert tree(tmp_path) == original


@pytest.mark.parametrize("scope", ["project", "global"])
def test_unreadable_instruction_is_reported_without_fake_provenance(
    catalog: Path, tmp_path: Path, scope: str
) -> None:
    source = catalog / "skills/unreadable/SKILL.md"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"\xff\xfeinvalid source")
    good = skill(catalog / "skills/good", "good")
    target = layout(tmp_path, scope)
    elements = parse_elements(["skill:unreadable", "skill:good"])
    plan = collect_dsh_elements(elements, target, catalog)
    assert plan.partial and plan.source_errors[0][0] == source
    apply_dsh_install(plan)
    assert (target.skills_dir / "good/SKILL.md").read_bytes() == good.read_bytes()
    report = json.loads(
        (target.resources_dir / "contributions/source-errors.json").read_bytes()
    )
    assert report["errors"][0]["path"] == str(source)
    assert "source_sha256" not in report["errors"][0]
    assert all(
        row["provenance"]["source"] != str(source)
        for row in read_dsh_inventory(target).source_records.values()
    )
    write(source, "---\nname: unreadable\ndescription: Fixed\n---\nFixed body.\n")
    fixed = collect_dsh_elements(elements, target, catalog)
    apply_dsh_install(fixed)
    assert not fixed.partial and (target.skills_dir / "unreadable/SKILL.md").is_file()
    assert json.loads(
        (target.resources_dir / "contributions/source-errors.json").read_bytes()
    ) == {"errors": []}


@pytest.mark.parametrize("scope", ["project", "global"])
def test_owned_rejected_skill_is_retired_and_corrected_source_retries(
    catalog: Path, tmp_path: Path, scope: str
) -> None:
    source = skill(catalog / "skills/previous", "previous")
    target = layout(tmp_path, scope)
    elements = parse_elements(["skill:previous"])
    apply_dsh_install(collect_dsh_elements(elements, target, catalog, mode="copy"))
    original = source.read_bytes()
    skill(source.parent, "previous", bad=True)
    partial = collect_dsh_elements(elements, target, catalog, mode="copy")
    before = tree(target.dsh_dir)
    with pytest.raises(ConfigError):
        apply_dsh_install(partial, strict=True)
    assert tree(target.dsh_dir) == before
    apply_dsh_install(partial)
    assert not (target.skills_dir / "previous").exists()
    assert "skills/previous" not in read_dsh_inventory(target).records
    assert (
        apply_dsh_install(
            collect_dsh_elements(elements, target, catalog, mode="copy")
        ).changed_paths
        == ()
    )
    source.write_bytes(original)
    recovered = collect_dsh_elements(elements, target, catalog, mode="copy")
    apply_dsh_install(recovered)
    assert not recovered.partial
    assert (target.skills_dir / "previous/SKILL.md").read_bytes() == original


def test_foreign_contents_prevent_retirement_and_all_partial_writes(
    catalog: Path, tmp_path: Path
) -> None:
    source = skill(catalog / "skills/previous", "previous")
    target = layout(tmp_path, "project")
    elements = parse_elements(["skill:previous"])
    apply_dsh_install(collect_dsh_elements(elements, target, catalog, mode="copy"))
    write(target.skills_dir / "previous/user-owned.txt", "User data")
    skill(source.parent, "previous", bad=True)
    partial = collect_dsh_elements(elements, target, catalog, mode="copy")
    before = tree(tmp_path)
    with pytest.raises(LinkError, match="Foreign/modified"):
        apply_dsh_install(partial)
    assert tree(tmp_path) == before


@pytest.mark.parametrize("mode", ["link", "copy"])
def test_unowned_rejected_bundle_cannot_enter_native_discovery(
    catalog: Path, tmp_path: Path, mode: str
) -> None:
    import shutil

    target = layout(tmp_path, "project")
    source = skill(catalog / "skills/rejected", "rejected", bad=True)
    destination = target.skills_dir / "rejected"
    destination.parent.mkdir(parents=True)
    if mode == "link":
        destination.symlink_to(source.parent)
    else:
        shutil.copytree(source.parent, destination)
    plan = collect_dsh_elements(parse_elements(["skill:rejected"]), target, catalog)
    before = tree(tmp_path)
    with pytest.raises(LinkError, match="Foreign DSH destination"):
        apply_dsh_install(plan)
    assert tree(tmp_path) == before


def test_unowned_rejected_nested_command_cannot_enter_native_discovery(
    catalog: Path, tmp_path: Path
) -> None:
    target = layout(tmp_path, "project")
    assert target.project_root is not None
    source = write(
        target.project_root / ".claude/commands/nested/source-name.md",
        "---\nname: native-name\ndescription: A rejected command\n"
        "disable-model-invocation: true\nallowed-tools: Bash\n---\nOriginal body.\n",
    )
    destination = target.skills_dir / "native-name.md"
    destination.parent.mkdir(parents=True)
    destination.symlink_to(source)
    before = tree(tmp_path)
    with pytest.raises(LinkError, match="Foreign DSH destination"):
        migrate_to_dsh(target.project_root)
    assert tree(tmp_path) == before


def test_local_migration_retains_failed_guard_diagnostics_and_healthy_siblings(
    catalog: Path, tmp_path: Path
) -> None:
    target = layout(tmp_path, "project")
    assert target.project_root is not None
    root = target.project_root
    write(root / ".claude/settings.local.json", json.dumps(settings()))
    skill(root / ".claude/skills/good", "good")
    skill(root / ".claude/skills/bad", "bad", bad=True)
    original = tree(root)
    with pytest.raises(ConfigError):
        migrate_to_dsh(root, strict=True)
    assert tree(root) == original
    report = migrate_to_dsh(root)
    assert report.partial and any(
        item.code == "HOOK_UNMAPPED" for item in report.skipped
    )
    assert report.plan.blocked  # Original guard gaps were never relabeled READY.
    assert (target.skills_dir / "good/SKILL.md").is_file()
    assert not (target.skills_dir / "bad").exists()
    assert migrate_to_dsh(root).changed_paths == ()
    assert tree(root / ".claude") == {
        key.removeprefix(".claude/"): value for key, value in original.items()
    }


@pytest.mark.parametrize("scope", ["project", "global"])
def test_actual_native_yaml_batch_isolates_one_failure(
    catalog: Path, tmp_path: Path, scope: str, dsh_native_runtime: Path
) -> None:
    valid = write(
        catalog / "skills/native-good/SKILL.md",
        "---\nname: native-good\ndescription: |\n  Valid native YAML\n"
        "---\nOriginal body.\n",
    )
    bad = write(
        catalog / "skills/native-bad/SKILL.md",
        "---\nname: native-bad\ndescription: [unterminated\n---\nOriginal bad body.\n",
    )
    runtime = resolve_dsh_runtime(dsh_native_runtime / "node_modules/@deepseek-ai/dsh")
    original = tree(catalog)
    metadata = native_frontmatter(
        runtime, [bad, valid], cwd=tmp_path, env={}, strict=False
    )
    assert valid in metadata and bad not in metadata and bad in metadata.errors
    target = layout(tmp_path, scope)
    plan = _collect_plan(
        parse_elements(["skill:native-bad", "skill:native-good"]),
        target,
        catalog,
        runtime,
        tmp_path,
        {},
        [Target.DSH],
    )
    assert [(item.status, item.provenance.source) for item in plan.skills] == [
        ("MANUAL", bad),
        ("READY", valid),
    ]
    assert (
        plan.skills[0].provenance.source_sha256
        == hashlib.sha256(bad.read_bytes()).hexdigest()
    )
    apply_dsh_install(plan)
    assert (
        target.skills_dir / "native-good/SKILL.md"
    ).read_bytes() == valid.read_bytes()
    assert not (target.skills_dir / "native-bad").exists()
    with pytest.raises(ConfigError, match="Native DSH inspection refused"):
        native_frontmatter(runtime, [bad, valid], cwd=tmp_path, env={}, strict=True)
    assert tree(catalog) == original


def test_native_managed_launch_with_skipped_protection_and_scope_siblings(
    managed_fixture: tuple[Path, Path, DshNativeRuntime, dict[str, str]],
    tmp_path: Path,
) -> None:
    project, profile, runtime, env = managed_fixture
    env["PYTHONPATH"] = str(Path(__file__).parents[2] / "src")
    storage = Path(env["AI_DOTFILES_HOME"])
    catalog = storage / "catalog"
    for scope in ("global", "project"):
        skill(catalog / f"skills/{scope}-good", f"{scope}-good")
        write(
            catalog / f"skills/{scope}-bad/SKILL.md",
            f"---\nname: {scope}-bad\ndescription: [unterminated\n---\nBad body.\n",
        )
        write(
            (
                storage / "global.json"
                if scope == "global"
                else project / "ai-dotfiles.json"
            ),
            json.dumps(
                {
                    "targets": ["dsh"],
                    "packages": [f"skill:{scope}-good", f"skill:{scope}-bad"],
                }
            ),
        )
    rejected_guard = settings()
    del rejected_guard["permissions"]
    rejected_guard["hooks"]["PreToolUse"][0]["hooks"].pop()
    write(project / ".claude/settings.local.json", json.dumps(rejected_guard))
    global_settings = write(
        storage / "global/settings.json",
        json.dumps({"permissions": {"defaultMode": "auto"}}),
    )
    global_settings_before = global_settings.read_bytes()
    global_manifest_before = (storage / "global.json").read_bytes()
    patch = profile / "cordis.patch.yml"
    patches = json.loads(patch.read_bytes())
    patches[0]["insert"].extend(
        [
            {"id": "skills", "name": "@deepseek-ai/dsh-skill"},
            {
                "id": "skill-filesystem",
                "name": "@deepseek-ai/dsh-skill-filesystem",
                "config": {"watch": False},
            },
        ]
    )
    patch.write_text(json.dumps(patches))
    originals = tree(catalog), tree(profile)
    with pytest.raises(ConfigError):
        prepare_dsh_launch(
            ["proof", "task"],
            cwd=project,
            process_env=env,
            runtime=runtime,
            strict=True,
        )
    assert not (project / ".dsh").exists()
    plan = prepare_dsh_launch(
        ["proof", "task"], cwd=project, process_env=env, runtime=runtime
    )
    assert plan.partial
    assert any(item.code == "HOOK_UNMAPPED" for item in plan.skipped)
    assert any(
        item.code == "FIELD_UNMAPPED"
        and item.field == "permissions['defaultMode']"
        and item.element == str(global_settings)
        for item in plan.skipped
    )
    assert {item["name"] for item in plan.request["requiredSkills"]} == {
        "global-good",
        "project-good",
    }
    assert "ai-dotfiles-hooks" not in {row["id"] for row in plan.config.rows}
    result = _run(plan, env, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "SKIPPED ERROR" in result.stderr
    assert "permissions['defaultMode']" in result.stderr
    events = [
        json.loads(line)["event"]
        for line in Path(env["PROOF"]).read_text().splitlines()
    ]
    assert events == ["ready", "include", "agent", "turn"]
    assert (tree(catalog), tree(profile)) == originals
    assert global_settings.read_bytes() == global_settings_before
    assert (storage / "global.json").read_bytes() == global_manifest_before

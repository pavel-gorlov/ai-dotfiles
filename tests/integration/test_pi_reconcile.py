"""Pi preflight, drift, and failure recovery through the project CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ai_dotfiles.core import manifest as project_manifest
from ai_dotfiles.core import pi_install
from ai_dotfiles.core.errors import LinkError
from tests.integration.test_pi_target import (
    OWNERSHIP,
    SKILLS,
    invoke,
    make_skill,
    write_project,
)
from tests.integration.test_pi_target import pi_project as _pi_project

pi_project = _pi_project


def test_pi_check_is_read_only_and_reports_source_generator_and_missing_drift(
    pi_project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, catalog = pi_project
    one = make_skill(catalog / "skills" / "one")
    make_skill(catalog / "skills" / "two")
    make_skill(catalog / "skills" / "three")
    manifest = write_project(project, ["pi"], ["skill:one", "skill:two", "skill:three"])
    invoke("install")
    registry = project / OWNERSHIP
    ownership = json.loads(registry.read_bytes())
    ownership["skills"][str(SKILLS / "two")]["generator"] = 2
    registry.write_text(json.dumps(ownership), encoding="utf-8")
    (one / "reference.md").write_text("new data", encoding="utf-8")
    link = project / SKILLS / "one"
    (project / SKILLS / "three").unlink()
    before = (manifest.read_bytes(), registry.read_bytes(), link.lstat().st_ino)
    for args in [("status",), ("reconcile", "--check", "--strict")]:
        output = invoke(*args, expected=1).output
        assert f"{SKILLS / 'one'} STALE (source changed)" in output
        assert f"{SKILLS / 'two'} STALE (generator changed)" in output
        assert f"{SKILLS / 'three'} MISSING" in output
        assert (
            manifest.read_bytes(),
            registry.read_bytes(),
            link.lstat().st_ino,
        ) == before
        assert not (project / SKILLS / "three").is_symlink()

    invoke("reconcile", "--strict")
    assert link.lstat().st_ino == before[2]
    invoke("status")
    invoke("reconcile", "--check", "--strict")

    old = pi_install.PI_SKILL_GENERATOR_VERSION
    monkeypatch.setattr(pi_install, "PI_SKILL_GENERATOR_VERSION", old + 1)
    assert "generator changed" in invoke("status", expected=1).output
    invoke("install")
    invoke("reconcile", "--check", "--strict")


def test_pi_retires_exact_broken_owned_link_and_rows_for_a_deleted_domain_member(
    pi_project: tuple[Path, Path],
) -> None:
    project, catalog = pi_project
    source = make_skill(catalog / "suite" / "skills" / "one")
    make_skill(catalog / "suite" / "skills" / "two")
    write_project(project, ["pi"], ["@suite"])
    invoke("install")
    link = project / SKILLS / "one"
    (source / "SKILL.md").unlink()
    source.rmdir()
    assert os.readlink(link) == str(source)
    assert f"{SKILLS / 'one'} RETIRED" in invoke("status", expected=1).output
    invoke("reconcile")
    assert not link.is_symlink()
    assert (project / SKILLS / "two").is_symlink()

    write_project(project, ["future"], [])
    assert (
        f"{SKILLS / 'two'} RETIRED" in invoke("reconcile", "--check", expected=1).output
    )
    invoke("install")
    assert not (project / OWNERSHIP).exists()
    assert not (project / SKILLS / "two").is_symlink()
    invoke("status")


def test_pi_missing_standalone_is_diagnosed_until_the_record_is_removed(
    pi_project: tuple[Path, Path],
) -> None:
    project, catalog = pi_project
    source = make_skill(catalog / "skills" / "fixture")
    write_project(project, ["pi"], ["skill:fixture"])
    invoke("install")
    (source / "SKILL.md").unlink()
    source.rmdir()
    assert str(source) in invoke("status", expected=1).output
    assert (project / SKILLS / "fixture").is_symlink()
    invoke("remove", "skill:fixture")
    assert not (project / SKILLS / "fixture").is_symlink()
    assert not (project / OWNERSHIP).exists()


@pytest.mark.parametrize(
    "conflict", ["real", "same-link", "pi-parent", "skills-parent"]
)
def test_pi_preflight_protects_foreign_paths_before_legacy_install_or_manifest(
    pi_project: tuple[Path, Path], tmp_path: Path, conflict: str
) -> None:
    project, catalog = pi_project
    skill = make_skill(catalog / "skills" / "fixture")
    manifest = write_project(project, ["codex", "pi", "future"], [])
    before = manifest.read_bytes()
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    sentinel = foreign / "keep"
    sentinel.write_bytes(b"user data")
    target = project / SKILLS / "fixture"
    if conflict == "pi-parent":
        (project / ".pi").symlink_to(foreign, target_is_directory=True)
    elif conflict == "skills-parent":
        (project / ".pi").mkdir()
        (project / SKILLS).symlink_to(foreign, target_is_directory=True)
    else:
        target.parent.mkdir(parents=True)
        if conflict == "real":
            target.write_bytes(b"user skill")
        else:
            target.symlink_to(skill, target_is_directory=True)
    invoke("add", "skill:fixture", expected=1)
    assert manifest.read_bytes() == before
    assert not (project / ".agents").exists()
    assert not (project / OWNERSHIP).exists()
    assert list(foreign.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"user data"
    if conflict == "real":
        assert target.read_bytes() == b"user skill"
    if conflict == "same-link":
        assert os.readlink(target) == str(skill)


def test_pi_preflight_rejects_swapped_owned_links_and_invalid_registry_paths(
    pi_project: tuple[Path, Path], tmp_path: Path
) -> None:
    project, catalog = pi_project
    source = make_skill(catalog / "skills" / "one")
    write_project(project, ["pi"], ["skill:one"])
    invoke("install")
    link = project / SKILLS / "one"
    before = (project / "ai-dotfiles.json").read_bytes()
    link.unlink()
    link.symlink_to(source / ".." / "one", target_is_directory=True)
    error = invoke("remove", "skill:one", expected=1).output
    assert f"replaced: {SKILLS / 'one'}" in error
    assert os.readlink(link) == str(source / ".." / "one")
    assert (project / "ai-dotfiles.json").read_bytes() == before

    registry = project / OWNERSHIP
    data = json.loads(registry.read_bytes())
    sentinel = tmp_path / "unrelated"
    sentinel.write_bytes(b"untouched")
    data["skills"][str(sentinel)] = data["skills"].pop(str(SKILLS / "one"))
    registry.write_text(json.dumps(data), encoding="utf-8")
    malformed = registry.read_bytes()
    error = invoke("reconcile", "--check", "--strict", expected=1).output
    assert "Invalid Pi ownership registry" in error
    assert sentinel.read_bytes() == b"untouched"
    assert registry.read_bytes() == malformed


@pytest.mark.parametrize(
    "fail_path", [SKILLS / "second", OWNERSHIP, Path("ai-dotfiles.json")]
)
def test_pi_only_add_rolls_back_published_paths_and_manifest(
    pi_project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, fail_path: Path
) -> None:
    project, catalog = pi_project
    make_skill(catalog / "skills" / "first")
    make_skill(catalog / "skills" / "second")
    manifest = write_project(project, ["pi", "future-target"], [])
    manifest.chmod(0o640)
    before = manifest.read_bytes()
    publish = pi_install._publish_new

    def fail_once(source: Path, destination: Path, **fds: int | None) -> None:
        if destination == project / fail_path and not failed:
            failed.append(destination)
            raise OSError("injected Pi publication fault")
        publish(source, destination, **fds)

    failed: list[Path] = []
    monkeypatch.setattr(pi_install, "_publish_new", fail_once)
    error = invoke("add", "skill:first", "skill:second", expected=1).output
    assert "injected Pi publication fault" in error
    assert "to complete Pi installation" not in error
    assert failed == [project / fail_path]
    assert manifest.read_bytes() == before
    assert manifest.stat().st_mode & 0o777 == 0o640
    assert not (project / ".pi").exists()
    assert not list(project.glob(".ai-dotfiles-pi-*"))
    invoke("add", "skill:first", "skill:second")
    invoke("reconcile", "--check", "--strict")


@pytest.mark.parametrize("verb", ["add", "remove", "install"])
def test_mixed_late_pi_failure_keeps_legacy_packages_and_install_recovers(
    pi_project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, verb: str
) -> None:
    project, catalog = pi_project
    original = make_skill(catalog / "skills" / "original")
    make_skill(catalog / "skills" / "new", depends="depends: [skill:original]\n")
    targets = ["codex", "future", "pi"]
    manifest = write_project(project, targets, ["skill:original"])
    invoke("install")
    registry = project / OWNERSHIP
    existing = registry.read_bytes()
    existing_link = project / SKILLS / "original"
    if verb == "install":
        assert invoke("remove", "skill:original").exit_code == 0
        manifest = write_project(project, targets, ["skill:new"])
        args = ("install",)
    elif verb == "add":
        args = ("add", "skill:new")
    else:
        args = ("remove", "skill:original")

    publish = pi_install._publish_new
    failed: list[Path] = []

    def fail_once(source: Path, destination: Path, **fds: int | None) -> None:
        if not failed and destination in {registry, project / SKILLS / "new"}:
            failed.append(destination)
            raise OSError("injected mixed Pi fault")
        publish(source, destination, **fds)

    monkeypatch.setattr(pi_install, "_publish_new", fail_once)
    if verb == "remove":
        move = pi_install._move_leaf

        def fail_registry_retirement(
            source: Path, destination: Path, **fds: int | None
        ) -> None:
            if not failed and source == registry:
                failed.append(source)
                raise OSError("injected mixed Pi fault")
            move(source, destination, **fds)

        monkeypatch.setattr(pi_install, "_move_leaf", fail_registry_retirement)

    error = invoke(*args, expected=1).output
    assert "injected mixed Pi fault" in error
    assert "Run 'ai-dotfiles install' to complete Pi installation." in error
    parsed = json.loads(manifest.read_bytes())
    assert parsed["targets"] == targets
    assert (
        parsed["packages"]
        == {
            "add": ["skill:original", "skill:new"],
            "remove": [],
            "install": ["skill:new", "skill:original"],
        }[verb]
    )
    if verb in {"add", "remove"}:
        assert registry.read_bytes() == existing
        assert os.readlink(existing_link) == str(original)
    else:
        assert not registry.exists()
        assert not existing_link.is_symlink()
    assert not (project / SKILLS / "new").is_symlink()
    assert (project / ".agents/skills/new/SKILL.md").exists() == (verb != "remove")
    assert (project / ".agents/skills/original/SKILL.md").exists() == (verb != "remove")
    invoke("install")
    invoke("status")
    invoke("reconcile", "--check", "--strict")


def test_pi_add_install_and_remove_preflight_before_dependency_manifest_or_custody(
    pi_project: tuple[Path, Path],
) -> None:
    project, catalog = pi_project
    required = make_skill(catalog / "skills" / "required")
    make_skill(catalog / "skills" / "primary", depends="depends: [skill:required]\n")
    manifest = write_project(project, ["pi"], ["skill:primary"])
    before = manifest.read_bytes()
    assert (
        "missing transitive dependencies"
        in invoke("install", "--strict-deps", expected=1).output
    )
    target = project / SKILLS / "required"
    target.parent.mkdir(parents=True)
    target.symlink_to(required, target_is_directory=True)
    assert "foreign" in invoke("install", expected=1).output
    assert manifest.read_bytes() == before
    target.unlink()

    invoke("install")
    before = manifest.read_bytes()
    target.unlink()
    target.write_bytes(b"user replacement")
    assert "foreign" in invoke("remove", "skill:primary", expected=1).output
    assert manifest.read_bytes() == before
    assert target.read_bytes() == b"user replacement"


def test_pi_rechecks_destination_snapshots_before_publication(
    pi_project: tuple[Path, Path],
) -> None:
    project, catalog = pi_project
    make_skill(catalog / "skills" / "fixture")
    packages = ["skill:fixture"]
    targets = ["pi"]
    manifest = write_project(project, targets, packages)
    before = manifest.read_bytes()
    plan = pi_install.plan_pi_project(project, packages, catalog, targets)
    assert plan is not None
    (project / ".pi").mkdir()
    foreign = project / ".pi" / "mcp.json"
    foreign.write_bytes(b"user resource")
    with pytest.raises(LinkError, match="directory changed after preflight"):
        pi_install.apply_pi_project(plan)
    assert foreign.read_bytes() == b"user resource"
    assert manifest.read_bytes() == before
    assert not (project / OWNERSHIP).exists()


def test_pi_only_remove_rollback_preserves_original_link_registry_and_manifest(
    pi_project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, catalog = pi_project
    source = make_skill(catalog / "suite" / "skills" / "fixture")
    manifest = write_project(project, ["pi"], ["@suite"])
    invoke("install")
    shim = catalog.parent / "bin" / "suite-tool"
    shim.parent.mkdir(exist_ok=True)
    shim.write_text("#!/bin/sh\n# managed-by: ai-dotfiles\n# domain: suite\n")
    venv = catalog.parent / "venvs" / "suite"
    venv.mkdir(parents=True)
    registry = project / OWNERSHIP
    before = (manifest.read_bytes(), registry.read_bytes())
    publish = pi_install._publish_new
    failed = False

    def fail_manifest(source: Path, destination: Path, **fds: int | None) -> None:
        nonlocal failed
        if destination == manifest and not failed:
            failed = True
            raise OSError("injected manifest publication fault")
        publish(source, destination, **fds)

    monkeypatch.setattr(pi_install, "_publish_new", fail_manifest)
    error = invoke("remove", "@suite", expected=1).output
    assert "injected manifest publication fault" in error
    assert (manifest.read_bytes(), registry.read_bytes()) == before
    assert os.readlink(project / SKILLS / "fixture") == str(source)
    assert shim.is_file()
    assert venv.is_dir()
    invoke("reconcile", "--check", "--strict")
    invoke("remove", "@suite")
    assert not registry.exists()
    assert not shim.exists()
    assert not venv.exists()


@pytest.mark.skipif(os.name != "posix", reason="project directory flock is POSIX")
def test_pi_concurrent_plans_cannot_overwrite_the_winning_commit(
    pi_project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event

    project, catalog = pi_project
    make_skill(catalog / "skills" / "first")
    make_skill(catalog / "skills" / "second")
    manifest = write_project(project, ["pi"], [])
    (project / SKILLS).mkdir(parents=True)
    first = pi_install.plan_pi_project(
        project, ["skill:first"], catalog, ["pi"], original_packages=[]
    )
    second = pi_install.plan_pi_project(
        project, ["skill:second"], catalog, ["pi"], original_packages=[]
    )
    assert first is not None and second is not None
    before_publish, release, second_started = Event(), Event(), Event()
    publish = pi_install._publish_new

    def pause_first(source: Path, destination: Path, **fds: int | None) -> None:
        if destination == project / SKILLS / "first":
            before_publish.set()
            assert release.wait(5)
        publish(source, destination, **fds)

    def apply_second() -> None:
        second_started.set()
        pi_install.apply_pi_project(second, manifest_change=["skill:second"])

    monkeypatch.setattr(pi_install, "_publish_new", pause_first)
    with ThreadPoolExecutor(max_workers=2) as executor:
        winning = executor.submit(
            pi_install.apply_pi_project, first, manifest_change=["skill:first"]
        )
        try:
            assert before_publish.wait(5)
            losing = executor.submit(apply_second)
            assert second_started.wait(5)
            with pytest.raises(TimeoutError):
                losing.result(timeout=0.1)
        finally:
            release.set()
        winning.result(timeout=5)
        with pytest.raises(LinkError, match="destination changed after preflight"):
            losing.result(timeout=5)

    assert json.loads(manifest.read_bytes())["packages"] == ["skill:first"]
    assert sorted(path.name for path in (project / SKILLS).iterdir()) == ["first"]
    invoke("reconcile", "--check", "--strict")


def test_mixed_pi_accepts_native_line_endings_from_legacy_manifest_writer(
    pi_project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, catalog = pi_project
    make_skill(catalog / "skills" / "fixture")
    manifest = write_project(project, ["claude", "pi"], [])
    write_manifest = project_manifest.write_manifest

    def write_crlf(path: Path, data: dict[str, object]) -> None:
        write_manifest(path, data)
        normalized = path.read_bytes().replace(b"\r\n", b"\n")
        path.write_bytes(normalized.replace(b"\n", b"\r\n"))

    monkeypatch.setattr(project_manifest, "write_manifest", write_crlf)

    invoke("add", "skill:fixture")
    assert b"\r\n" in manifest.read_bytes()
    assert (project / SKILLS / "fixture").is_symlink()
    invoke("remove", "skill:fixture")
    assert json.loads(manifest.read_bytes())["packages"] == []
    assert not (project / SKILLS / "fixture").is_symlink()


@pytest.mark.parametrize("layout", ["directory", "nested", "direct-markdown"])
def test_pi_refuses_a_user_skill_with_the_same_native_name(
    pi_project: tuple[Path, Path], layout: str
) -> None:
    project, catalog = pi_project
    make_skill(catalog / "skills" / "fixture", name="shared-command")
    manifest = write_project(project, ["pi"], [])
    skills = project / SKILLS
    if layout == "direct-markdown":
        skills.mkdir(parents=True)
        foreign = skills / "personal.md"
        foreign.write_text(
            "---\nname: shared-command # personal variant\n"
            "description: User skill.\n---\n"
        )
    else:
        bundle = "personal" if layout == "directory" else "private/personal"
        foreign = (
            make_skill(skills / bundle, name="shared-command # personal variant")
            / "SKILL.md"
        )
    original = (manifest.read_bytes(), foreign.read_bytes())

    output = invoke("add", "skill:fixture", expected=1).output

    assert "Pi skill name collision 'shared-command'" in output
    assert str(foreign) in output
    assert (manifest.read_bytes(), foreign.read_bytes()) == original
    assert not (skills / "fixture").exists()
    assert not (project / OWNERSHIP).exists()


def test_pi_reconcile_refuses_a_new_user_skill_collision(
    pi_project: tuple[Path, Path],
) -> None:
    project, catalog = pi_project
    make_skill(catalog / "skills" / "fixture")
    write_project(project, ["pi"], ["skill:fixture"])
    invoke("install")
    registry = project / OWNERSHIP
    before = registry.read_bytes()
    make_skill(project / SKILLS / "private", name="fixture")

    assert "name collision" in invoke("reconcile", expected=1).output
    assert registry.read_bytes() == before
    assert (project / SKILLS / "fixture").is_symlink()


def test_pi_never_clobbers_a_new_leaf_after_its_last_check(
    pi_project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, catalog = pi_project
    make_skill(catalog / "skills" / "fixture")
    manifest = write_project(project, ["pi"], [])
    original = manifest.read_bytes()
    destination = project / SKILLS / "fixture"
    destination.parent.mkdir(parents=True)
    publish = pi_install._publish_new

    def create_private_then_publish(
        source: Path, target: Path, **fds: int | None
    ) -> None:
        if target == destination:
            target.write_bytes(b"user saved a resource")
        publish(source, target, **fds)

    monkeypatch.setattr(pi_install, "_publish_new", create_private_then_publish)
    invoke("add", "skill:fixture", expected=1)

    assert destination.read_bytes() == b"user saved a resource"
    assert manifest.read_bytes() == original
    assert not (project / OWNERSHIP).exists()
    assert not list(project.glob(".ai-dotfiles-pi-*"))


@pytest.mark.skipif(os.name != "posix", reason="tests a POSIX directory rename")
def test_pi_publish_is_bound_to_the_verified_parent(
    pi_project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project, catalog = pi_project
    make_skill(catalog / "skills" / "fixture")
    manifest = write_project(project, ["pi"], [])
    original = manifest.read_bytes()
    skills = project / SKILLS
    skills.mkdir(parents=True)
    moved = skills.with_name("moved-skills")
    outside = tmp_path / "private"
    outside.mkdir()
    sentinel = outside / "fixture"
    sentinel.write_bytes(b"private outside resource")
    publish = pi_install._publish_new

    def substitute_parent(path: Path, destination: Path, **fds: int | None) -> None:
        if destination == skills / "fixture":
            skills.rename(moved)
            skills.symlink_to(outside, target_is_directory=True)
        publish(path, destination, **fds)

    monkeypatch.setattr(pi_install, "_publish_new", substitute_parent)
    assert "directory changed" in invoke("add", "skill:fixture", expected=1).output
    assert sentinel.read_bytes() == b"private outside resource"
    assert not list(moved.iterdir())
    assert manifest.read_bytes() == original
    assert not (project / OWNERSHIP).exists()

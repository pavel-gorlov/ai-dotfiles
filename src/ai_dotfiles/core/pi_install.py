"""Project-scoped Pi resources, ownership, and transactional publication."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_dotfiles.core.elements import (
    Element,
    ElementType,
    parse_elements,
    resolve_source_path,
)
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError, LinkError, SourceError
from ai_dotfiles.core.frontmatter import parse_frontmatter
from ai_dotfiles.core.paths import project_manifest_path
from ai_dotfiles.core.pi_hooks import (
    PI_HOOK_GENERATOR_VERSION,
    PiHookPlan,
    collect_pi_hooks,
)
from ai_dotfiles.core.targets import Target

PI_SKILL_GENERATOR_VERSION = 1
_OWNERSHIP_VERSION = 1
_PI = Path(".pi")
_SKILLS = _PI / "skills"
_HOOKS = _PI / "extensions" / "ai-dotfiles-hooks.js"
_OWNERSHIP = _PI / ".ai-dotfiles-ownership.json"
_LEGACY_TARGETS = {Target.CLAUDE.value, Target.CODEX.value, Target.DSH.value}
type FileContent = bytes | str | None  # regular file, symlink, or absent


@dataclass(frozen=True)
class _Skill:
    source: str  # relative to the catalog
    link: str  # exact symlink text
    fingerprint: str
    generator: int


@dataclass(frozen=True)
class _HookOwnership:
    sha256: str
    fingerprint: str
    generator: int


@dataclass(frozen=True)
class _FileStamp:
    device: int
    inode: int
    mode: int
    size: int
    modified: int
    changed: int

    @classmethod
    def from_stat(cls, entry: os.stat_result) -> _FileStamp:
        return cls(
            entry.st_dev,
            entry.st_ino,
            entry.st_mode,
            entry.st_size,
            entry.st_mtime_ns,
            entry.st_ctime_ns,
        )

    def identity(self) -> tuple[int, int, int]:
        return self.device, self.inode, self.mode


@dataclass(frozen=True)
class _Snapshot:
    stamp: _FileStamp | None
    content: FileContent


@dataclass(frozen=True)
class PiFileChange:
    """One bounded path change, with the preflight state needed for rollback."""

    path: Path  # project-relative
    before: _Snapshot
    after: FileContent


@dataclass(frozen=True)
class PiReport:
    resources: tuple[Path, ...]  # project-relative paths
    drift: tuple[str, ...]
    skipped: tuple[str, ...]
    changed_paths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class PiPlan:
    root: Path
    catalog: Path
    storage_root: Path
    packages: tuple[str, ...]
    enabled: bool
    has_legacy_target: bool
    initial_manifest: _Snapshot
    updated_manifest: bytes | None
    parents: dict[Path, _FileStamp | None]
    leaves: dict[Path, _Snapshot]
    skills: dict[Path, _Skill]
    hooks: PiHookPlan | None
    changes: tuple[PiFileChange, ...]
    report: PiReport


def _lstat(path: Path) -> _FileStamp | None:
    try:
        return _FileStamp.from_stat(path.lstat())
    except FileNotFoundError:
        return None


def _real_dir(path: Path, stamp: _FileStamp | None, *, source: bool = False) -> None:
    if stamp is not None and stat.S_ISDIR(stamp.mode):
        return
    error = SourceError if source else ConfigError
    raise error(f"Pi requires a real directory at {path}")


def _source_dir(catalog: Path, path: Path, *, optional: bool = False) -> bool:
    current = catalog
    _real_dir(current, _lstat(current), source=True)
    for part in path.relative_to(catalog).parts:
        current /= part
        stamp = _lstat(current)
        if stamp is None and optional:
            return False
        _real_dir(current, stamp, source=True)
    return True


def _read_file(path: Path, stamp: _FileStamp) -> bytes:
    # Refuse a substituted symlink or special file before reading any content.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        if _FileStamp.from_stat(os.fstat(stream.fileno())) != stamp:
            raise ConfigError(f"Pi file changed during preflight: {path}")
        content = stream.read()
        if _FileStamp.from_stat(os.fstat(stream.fileno())) != stamp:
            raise ConfigError(f"Pi file changed during preflight: {path}")
    return content


def _snapshot(path: Path, *, read_file: bool = False) -> _Snapshot:
    stamp = _lstat(path)
    content: FileContent = None
    if stamp is not None:
        if stat.S_ISLNK(stamp.mode):
            content = os.readlink(path)
        elif read_file and stat.S_ISREG(stamp.mode):
            content = _read_file(path, stamp)
        if _lstat(path) != stamp:
            raise ConfigError(f"Pi path changed during preflight: {path}")
    return _Snapshot(stamp, content)


def _bundle_metadata(bundle: Path) -> tuple[str, str]:
    """Hash the full tree and validate simple in-bundle symlinks."""
    digest = hashlib.sha256()
    directories: dict[Path, list[Path]] = {}
    files: dict[Path, _FileStamp] = {}
    links: dict[Path, str] = {}
    resolved_links: dict[Path, Path] = {}

    def visit(path: Path) -> None:
        stamp = _lstat(bundle / path)
        if stamp is None:
            raise SourceError(f"Pi bundle entry disappeared: {bundle / path}")
        data: bytes = b""
        if stat.S_ISDIR(stamp.mode):
            children = sorted(
                entry.relative_to(bundle) for entry in (bundle / path).iterdir()
            )
            directories[path] = []
            for child in children:
                visit(child)
                if child in directories:
                    directories[path].append(child)
        elif stat.S_ISREG(stamp.mode):
            data = _read_file(bundle / path, stamp)
            files[path] = stamp
        elif stat.S_ISLNK(stamp.mode):
            target = os.readlink(bundle / path)
            links[path] = target
            data = os.fsencode(target)
        else:
            raise SourceError(f"Unsupported Pi bundle entry type: {bundle / path}")
        # Framed fields distinguish different paths/modes/content unambiguously.
        for field in (os.fsencode(path.as_posix()), str(stamp.mode).encode(), data):
            digest.update(len(field).to_bytes(8, "big"))
            digest.update(field)

    visit(Path("."))

    def resolve_link(link: Path, chain: frozenset[Path]) -> Path:
        if link in chain:
            raise SourceError(f"Cyclic Pi bundle symlink: {bundle / link}")
        if link in resolved_links:
            return resolved_links[link]
        raw = links[link]
        if Path(raw).anchor:
            raise SourceError(
                f"Pi bundle symlink escapes its directory: {bundle / link} -> {raw}"
            )
        current = link.parent
        for part in raw.replace(os.sep, "/").split("/"):
            if current not in directories:
                raise SourceError(f"Broken Pi bundle symlink: {bundle / link} -> {raw}")
            if part == "..":
                if current == Path("."):
                    raise SourceError(
                        f"Pi bundle symlink escapes its directory: "
                        f"{bundle / link} -> {raw}"
                    )
                current = current.parent
            elif part not in ("", "."):
                current /= part
                if current in links:
                    current = resolve_link(current, chain | {link})
        if current not in directories and current not in files:
            raise SourceError(f"Broken Pi bundle symlink: {bundle / link} -> {raw}")
        resolved_links[link] = current
        return current

    for entry in links:
        target = resolve_link(entry, frozenset())
        if target in directories:
            directories[entry.parent].append(target)

    visited: set[Path] = set()
    active: set[Path] = set()

    def check_cycles(path: Path) -> None:
        if path in active:
            raise SourceError(f"Cyclic Pi directory symlink in {bundle / path}")
        if path in visited:
            return
        active.add(path)
        for child in directories[path]:
            check_cycles(child)
        active.remove(path)
        visited.add(path)

    check_cycles(Path("."))
    skill_file = Path("SKILL.md")
    resolved_skill = resolved_links.get(skill_file, skill_file)
    if resolved_skill not in files:
        raise SourceError(f"Missing Pi skill source: {bundle / skill_file}")
    try:
        content = _read_file(bundle / resolved_skill, files[resolved_skill])
        text = content.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as exc:
        raise SourceError(
            f"Cannot decode Pi skill source {bundle / skill_file}: {exc}"
        ) from exc
    name = parse_frontmatter(text).get("name")
    return (name if isinstance(name, str) and name else bundle.name, digest.hexdigest())


def _bundle_sources(element: Element, catalog: Path) -> Iterator[Path]:
    if element.type is ElementType.SKILL:
        source = resolve_source_path(element, catalog)
        _source_dir(catalog, source)
        yield source
    elif element.type is ElementType.DOMAIN:
        domain = resolve_source_path(element, catalog)
        _source_dir(catalog, domain)
        skills = domain / "skills"
        if not _source_dir(catalog, skills, optional=True):
            return
        for entry in sorted(skills.iterdir()):
            if entry.name.startswith(".") or entry.name == "README.md":
                continue
            stamp = _lstat(entry)
            if stamp is None or stat.S_ISREG(stamp.mode):
                continue
            _real_dir(entry, stamp, source=True)
            if _lstat(entry / "SKILL.md") is not None:
                yield entry


def _skill_skips(element: Element, catalog: Path) -> Iterator[str]:
    if element.type in (ElementType.AGENT, ElementType.RULE):
        yield f"{element.raw}: no native Pi catalog adapter"
    elif element.type is ElementType.DOMAIN:
        domain = resolve_source_path(element, catalog)
        for subdir in ("agents", "rules"):
            location = domain / subdir
            stamp = _lstat(location)
            if stamp is not None and stat.S_ISDIR(stamp.mode):
                for member in sorted(location.glob("*.md")):
                    if member.name != "README.md" and not member.name.startswith("."):
                        relative = member.relative_to(catalog)
                        yield f"{relative}: no native Pi catalog adapter"


def _collect_skills(
    elements: Iterable[Element], catalog: Path
) -> tuple[dict[Path, _Skill], tuple[str, ...]]:
    skills: dict[Path, _Skill] = {}
    names: dict[str, Path] = {}
    seen_sources: set[Path] = set()
    skipped: list[str] = []
    for element in elements:
        for bundle in _bundle_sources(element, catalog):
            if bundle in seen_sources:
                continue
            source = bundle.relative_to(catalog).as_posix()
            destination = _SKILLS / bundle.name
            name, fingerprint = _bundle_metadata(bundle)
            seen_sources.add(bundle)
            if destination in skills:
                raise SourceError(
                    f"Pi skill destination collision at {destination}: "
                    f"{skills[destination].source} and {source}"
                )
            if name in names:
                raise SourceError(
                    f"Pi skill name collision {name!r}: "
                    f"{skills[names[name]].source} and {source}"
                )
            names[name] = destination
            skills[destination] = _Skill(
                source, str(bundle), fingerprint, PI_SKILL_GENERATOR_VERSION
            )
        skipped.extend(_skill_skips(element, catalog))
    return skills, tuple(dict.fromkeys(skipped))


def iter_pi_skill_pairs(
    element: Element, project_root: Path, catalog: Path
) -> Iterator[tuple[Path, Path]]:
    """Resolve the complete bundle paths discoverable by native Pi."""
    try:
        skills, _ = _collect_skills([element], catalog.resolve())
    except OSError as exc:
        raise SourceError(f"Cannot read Pi catalog {catalog}: {exc}") from exc
    for path, skill in skills.items():
        yield Path(skill.link), project_root / path


def _unique_json(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate property {key!r}")
        result[key] = value
    return result


def _load_ownership(
    snapshot: _Snapshot,
) -> tuple[dict[Path, _Skill], _HookOwnership | None]:
    if snapshot.stamp is None:
        return {}, None
    try:
        if not isinstance(snapshot.content, bytes):
            raise ValueError("expected a regular file")
        raw = json.loads(snapshot.content, object_pairs_hook=_unique_json)
        if (
            not isinstance(raw, dict)
            or raw.keys() not in ({"version", "skills"}, {"version", "skills", "hooks"})
            or type(raw["version"]) is not int
            or raw["version"] != _OWNERSHIP_VERSION
            or not isinstance(raw["skills"], dict)
        ):
            raise ValueError("unknown registry format")
        result: dict[Path, _Skill] = {}
        for label, row in raw["skills"].items():
            path = Path(label)
            if (
                label != path.as_posix()
                or path.parent != _SKILLS
                or path.name.startswith(".")
                or "\x00" in label
                or not isinstance(row, dict)
                or row.keys() != {"source", "link", "fingerprint", "generator"}
            ):
                raise ValueError(f"invalid entry {label!r}")
            source, link = row["source"], row["link"]
            fingerprint, generator = row["fingerprint"], row["generator"]
            if (
                not isinstance(source, str)
                or not isinstance(link, str)
                or not isinstance(fingerprint, str)
                or type(generator) is not int
                or generator <= 0
                or re.fullmatch("[a-f0-9]{64}", fingerprint) is None
            ):
                raise ValueError(f"invalid entry {label!r}")
            source_path, link_path = Path(source), Path(link)
            if (
                "\x00" in source
                or "\x00" in link
                or source != source_path.as_posix()
                or source_path.anchor
                or len(source_path.parts) not in (2, 3)
                or source_path.parts[-2:] != ("skills", path.name)
                or ".." in source_path.parts
                or not link_path.is_absolute()
                or str(link_path) != link
                or ".." in link_path.parts
                or link_path.parts[-len(source_path.parts) :] != source_path.parts
            ):
                raise ValueError(f"invalid catalog link for {label!r}")
            result[path] = _Skill(source, link, fingerprint, generator)
        hooks = None
        if "hooks" in raw:
            row = raw["hooks"]
            if not isinstance(row, dict) or row.keys() != {
                "sha256",
                "fingerprint",
                "generator",
            }:
                raise ValueError("invalid hooks entry")
            checksum, fingerprint, generator = (
                row["sha256"],
                row["fingerprint"],
                row["generator"],
            )
            if (
                not isinstance(checksum, str)
                or re.fullmatch("[a-f0-9]{64}", checksum) is None
                or not isinstance(fingerprint, str)
                or re.fullmatch("[a-f0-9]{64}", fingerprint) is None
                or type(generator) is not int
                or generator <= 0
            ):
                raise ValueError("invalid hooks entry")
            hooks = _HookOwnership(checksum, fingerprint, generator)
        return result, hooks
    except ValueError as exc:
        raise ConfigError(f"Invalid Pi ownership registry {_OWNERSHIP}: {exc}") from exc


def _json_bytes(data: object, *, sort_keys: bool = False) -> bytes:
    return (json.dumps(data, indent=2, sort_keys=sort_keys) + "\n").encode("utf-8")


def _collect_hooks(
    storage_root: Path, elements: Iterable[Element]
) -> PiHookPlan | None:
    return collect_pi_hooks(
        storage_root,
        (element.name for element in elements if element.type is ElementType.DOMAIN),
    )


def _plan_hooks(
    root: Path,
    hooks: PiHookPlan | None,
    recorded: _HookOwnership | None,
    parents: dict[Path, _FileStamp | None],
    leaves: dict[Path, _Snapshot],
    changes: list[PiFileChange],
    drift: list[str],
) -> _HookOwnership | None:
    if hooks is None and recorded is None:
        return None

    parent = _HOOKS.parent
    stamp = _lstat(root / parent)
    if stamp is not None:
        _real_dir(root / parent, stamp)
    parents[parent] = stamp

    current = _snapshot(root / _HOOKS, read_file=True)
    leaves[_HOOKS] = current
    checksum = (
        hashlib.sha256(current.content).hexdigest()
        if isinstance(current.content, bytes)
        else None
    )
    if current.stamp is not None and (recorded is None or checksum != recorded.sha256):
        raise ConfigError(f"Pi destination is foreign or was replaced: {_HOOKS}")

    if hooks is None:
        drift.append(f"{_HOOKS} RETIRED (no longer selected)")
        if current.stamp is not None:
            changes.append(PiFileChange(_HOOKS, current, None))
        return None

    wanted = _HookOwnership(
        hashlib.sha256(hooks.content).hexdigest(),
        hooks.fingerprint,
        PI_HOOK_GENERATOR_VERSION,
    )
    if current.stamp is None:
        drift.append(f"{_HOOKS} MISSING")
    elif recorded is not None:
        if recorded.generator != wanted.generator:
            drift.append(f"{_HOOKS} STALE (generator changed)")
        elif recorded.fingerprint != wanted.fingerprint:
            drift.append(f"{_HOOKS} STALE (source changed)")
        elif checksum != wanted.sha256:
            drift.append(f"{_HOOKS} STALE (generated content changed)")
    if current.content != hooks.content:
        changes.append(PiFileChange(_HOOKS, current, hooks.content))
    return wanted


def _plan_pi_project(
    root: Path,
    packages: Sequence[str],
    catalog: Path,
    targets: Sequence[str],
    original_packages: Sequence[str] | None,
) -> PiPlan | None:
    enabled = Target.PI.value in targets
    if not enabled:
        pi_stamp = _lstat(root / _PI)
        if pi_stamp is None or not stat.S_ISDIR(pi_stamp.mode):
            return None
        if _lstat(root / _OWNERSHIP) is None:
            return None

    parents: dict[Path, _FileStamp | None] = {}
    for path in (Path("."), _PI, _SKILLS):
        stamp = _lstat(root / path)
        if stamp is not None or path == Path("."):
            _real_dir(root / path, stamp)
        parents[path] = stamp

    registry = _snapshot(root / _OWNERSHIP, read_file=True)
    recorded, recorded_hooks = _load_ownership(registry)
    manifest_path = project_manifest_path(root)
    initial_manifest = _snapshot(manifest_path, read_file=True)
    if not isinstance(initial_manifest.content, bytes):
        raise ConfigError(f"Pi requires a regular manifest file at {manifest_path}")
    data = json.loads(initial_manifest.content)
    expected_packages = original_packages if original_packages is not None else packages
    if (
        not isinstance(data, dict)
        or data.get("packages", []) != list(expected_packages)
        or data.get("targets", [Target.CLAUDE.value]) != list(targets)
    ):
        raise ConfigError(f"Pi manifest changed before preflight: {manifest_path}")
    updated_manifest = None
    if list(packages) != list(expected_packages):
        data["packages"] = list(packages)
        updated_manifest = _json_bytes(data)

    storage_root = catalog.parent.absolute()
    if enabled:
        catalog = catalog.resolve()
    elements = parse_elements(list(packages)) if enabled else []
    skills, skipped = _collect_skills(elements, catalog)
    hooks = _collect_hooks(storage_root, elements)
    changes: list[PiFileChange] = []
    leaves = {_OWNERSHIP: registry}
    drift: list[str] = []
    for path in sorted(skills.keys() | recorded.keys()):
        current = _snapshot(root / path)
        leaves[path] = current
        wanted, previous = skills.get(path), recorded.get(path)
        if current.stamp is not None and (
            previous is None or current.content != previous.link
        ):
            raise ConfigError(f"Pi destination is foreign or was replaced: {path}")
        if wanted is None:
            drift.append(f"{path} RETIRED (no longer selected)")
            if current.stamp is not None:
                changes.append(PiFileChange(path, current, None))
        elif current.stamp is None:
            drift.append(f"{path} MISSING")
            changes.append(PiFileChange(path, current, wanted.link))
        elif previous is not None:
            if previous.link != wanted.link:
                drift.append(f"{path} STALE (source moved)")
                changes.append(PiFileChange(path, current, wanted.link))
            elif previous.generator != wanted.generator:
                drift.append(f"{path} STALE (generator changed)")
            elif previous.fingerprint != wanted.fingerprint:
                drift.append(f"{path} STALE (source changed)")

    hook_ownership = _plan_hooks(
        root, hooks, recorded_hooks, parents, leaves, changes, drift
    )
    has_resources = bool(skills) or hook_ownership is not None
    if (
        skills != recorded
        or hook_ownership != recorded_hooks
        or (not has_resources and registry.stamp is not None)
    ):
        updated_ownership: dict[str, object] = {
            "version": _OWNERSHIP_VERSION,
            "skills": {
                path.as_posix(): asdict(value) for path, value in skills.items()
            },
        }
        if hook_ownership is not None:
            updated_ownership["hooks"] = asdict(hook_ownership)
        updated_registry = (
            _json_bytes(updated_ownership, sort_keys=True) if has_resources else None
        )
        changes.append(PiFileChange(_OWNERSHIP, registry, updated_registry))
        if not drift:
            drift.append(f"{_OWNERSHIP} STALE (no resources remain)")

    resources = set(skills)
    if hooks is not None:
        resources.add(_HOOKS)
    return PiPlan(
        root,
        catalog,
        storage_root,
        tuple(packages),
        enabled,
        bool(_LEGACY_TARGETS.intersection(targets)),
        initial_manifest,
        updated_manifest,
        parents,
        leaves,
        skills,
        hooks,
        tuple(changes),
        PiReport(tuple(sorted(resources)), tuple(drift), skipped),
    )


def plan_pi_project(
    root: Path | None,
    packages: Sequence[str],
    catalog: Path,
    targets: Sequence[str],
    *,
    original_packages: Sequence[str] | None = None,
) -> PiPlan | None:
    """Plan and verify the selected project resources without writing anything."""
    if root is None:
        return None
    try:
        return _plan_pi_project(
            root.resolve(), packages, catalog, targets, original_packages
        )
    except (OSError, ValueError, RuntimeError) as exc:
        raise ConfigError(f"Cannot preflight Pi project {root}: {exc}") from exc


def _assert_parents(
    root: Path, path: Path, parents: dict[Path, _FileStamp | None]
) -> None:
    for parent in reversed(path.parents):
        actual, expected = _lstat(root / parent), parents[parent]
        if (
            actual is None
            and expected is not None
            or actual is not None
            and (expected is None or actual.identity() != expected.identity())
        ):
            raise ConfigError(
                f"Pi destination directory changed after preflight: {parent}"
            )


def _assert_leaf(root: Path, path: Path, expected: _Snapshot) -> None:
    actual = _snapshot(root / path, read_file=isinstance(expected.content, bytes))
    if actual != expected:
        raise ConfigError(f"Pi destination changed after preflight: {path}")


def _stage(path: Path, content: FileContent, mode: int) -> None:
    if isinstance(content, str):
        path.symlink_to(content, target_is_directory=True)
    elif isinstance(content, bytes):
        path.write_bytes(content)
        path.chmod(stat.S_IMODE(mode))


def _stage_change(
    directory: Path, index: int, change: PiFileChange
) -> tuple[Path, Path, _Snapshot]:
    after = directory / f"{index}.new"
    before = directory / f"{index}.old"
    mode = change.before.stamp.mode if change.before.stamp is not None else 0o600
    _stage(after, change.after, mode)
    _stage(before, change.before.content, mode)
    return after, before, _snapshot(after, read_file=isinstance(change.after, bytes))


def _apply_changes(plan: PiPlan, changes: list[PiFileChange]) -> None:
    parents = plan.parents.copy()
    created: list[Path] = []
    # The transaction directory is outside the Pi discovery trees.
    with tempfile.TemporaryDirectory(prefix=".ai-dotfiles-pi-", dir=plan.root) as temp:
        directory = Path(temp)
        staged = [
            _stage_change(directory, index, change)
            for index, change in enumerate(changes)
        ]
        applied: list[tuple[Path, Path, _Snapshot]] = []
        try:
            for change, (after, before, written) in zip(changes, staged, strict=True):
                _assert_parents(plan.root, change.path, parents)
                _assert_leaf(plan.root, change.path, change.before)
                if change.after is None:
                    (plan.root / change.path).unlink()
                else:
                    for parent in reversed(change.path.parents):
                        if parents[parent] is None:
                            (plan.root / parent).mkdir()
                            parents[parent] = _lstat(plan.root / parent)
                            created.append(parent)
                    _assert_parents(plan.root, change.path, parents)
                    _assert_leaf(plan.root, change.path, change.before)
                    os.replace(after, plan.root / change.path)
                applied.append((change.path, before, written))
        except (AiDotfilesError, OSError) as exc:
            failed: list[str] = []
            for path, before, written in reversed(applied):
                try:
                    _assert_parents(plan.root, path, parents)
                    current = _snapshot(
                        plan.root / path, read_file=isinstance(written.content, bytes)
                    )
                    # Rename may change ctime. Identity, mode, mtime, and content
                    # identify this publication without losing a concurrent edit.
                    if (
                        current.content != written.content
                        or current.stamp is None
                        and written.stamp is not None
                        or current.stamp is not None
                        and (
                            written.stamp is None
                            or current.stamp.identity() != written.stamp.identity()
                            or current.stamp.modified != written.stamp.modified
                        )
                    ):
                        raise ConfigError("changed since publication")
                    if _lstat(before) is not None:
                        os.replace(before, plan.root / path)
                    else:
                        (plan.root / path).unlink()
                except (AiDotfilesError, OSError) as rollback_error:
                    failed.append(f"{path}: {rollback_error}")

            for path in reversed(created):
                try:
                    _assert_parents(plan.root, path / "child", parents)
                    (plan.root / path).rmdir()
                except (AiDotfilesError, OSError) as rollback_error:
                    failed.append(f"{path}: {rollback_error}")
            suffix = f"; rollback incomplete ({'; '.join(failed)})" if failed else ""
            raise LinkError(f"{exc}{suffix}") from exc


@contextmanager
def _project_write_lock(root: Path) -> Iterator[None]:
    """Serialize Pi commits on POSIX without adding a project lock file."""
    if os.name != "posix":
        yield
        return

    import fcntl

    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _commit_plan(
    plan: PiPlan, manifest_path: Path, manifest_change: Sequence[str] | None
) -> list[PiFileChange]:
    changes = list(plan.changes)
    if manifest_change is not None:
        if plan.has_legacy_target or tuple(manifest_change) != plan.packages:
            raise ConfigError("Pi project manifest change does not match preflight")
        if plan.updated_manifest is not None:
            changes.append(
                PiFileChange(
                    manifest_path, plan.initial_manifest, plan.updated_manifest
                )
            )

    _assert_parents(plan.root, manifest_path, plan.parents)
    if manifest_change is None and plan.updated_manifest is not None:
        current = _snapshot(plan.root / manifest_path, read_file=True)
        if current.content != plan.updated_manifest:
            raise ConfigError(f"Pi manifest changed after preflight: {manifest_path}")
    else:
        _assert_leaf(plan.root, manifest_path, plan.initial_manifest)
    for path, expected in plan.leaves.items():
        _assert_parents(plan.root, path, plan.parents)
        _assert_leaf(plan.root, path, expected)
    if plan.enabled and changes:
        elements = parse_elements(list(plan.packages))
        skills, _ = _collect_skills(elements, plan.catalog)
        if skills != plan.skills:
            raise ConfigError("Pi skill sources changed after preflight")
        if _collect_hooks(plan.storage_root, elements) != plan.hooks:
            raise ConfigError("Pi hook sources changed after preflight")
    if changes:
        _apply_changes(plan, changes)
    return changes


def apply_pi_project(
    plan: PiPlan,
    *,
    manifest_change: Sequence[str] | None = None,
) -> PiReport:
    """Publish the plan, committing a Pi-only package change as the last file."""
    manifest_path = project_manifest_path(plan.root).relative_to(plan.root)
    try:
        with _project_write_lock(plan.root):
            changes = _commit_plan(plan, manifest_path, manifest_change)
    except (AiDotfilesError, OSError) as exc:
        recovery = (
            " Run 'ai-dotfiles install' to complete Pi installation."
            if plan.has_legacy_target
            else ""
        )
        raise LinkError(f"Pi installation failed: {exc}.{recovery}") from exc

    return PiReport(
        plan.report.resources,
        plan.report.drift,
        plan.report.skipped,
        tuple(change.path for change in changes if change.path != manifest_path),
    )

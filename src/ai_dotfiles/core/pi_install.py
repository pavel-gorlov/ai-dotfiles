"""Project-scoped Pi resources, ownership, and transactional publication."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import sys
import tempfile
from collections.abc import Iterable, Iterator, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from ai_dotfiles.core.elements import (
    Element,
    ElementType,
    parse_elements,
    resolve_source_path,
)
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError, LinkError, SourceError
from ai_dotfiles.core.gitignore import anchored_path_pattern
from ai_dotfiles.core.paths import project_manifest_path
from ai_dotfiles.core.pi_hooks import (
    PI_HOOK_GENERATOR_VERSION,
    PiHookPlan,
    collect_pi_hooks,
)
from ai_dotfiles.core.pi_mcp import (
    PI_MCP_PATH,
    PiMcpOwnership,
    PiMcpPlan,
    collect_pi_mcp,
    is_generated_mcp_file,
    load_mcp_ownership,
    plan_mcp_update,
    unique_json,
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
    mcp: PiMcpPlan | None
    changes: tuple[PiFileChange, ...]
    report: PiReport


def _at(path: Path, parent: int | None) -> Path:
    return path if parent is None else Path(path.name)


def _lstat(path: Path, *, parent: int | None = None) -> _FileStamp | None:
    try:
        return _FileStamp.from_stat(os.lstat(_at(path, parent), dir_fd=parent))
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


def _read_file(path: Path, stamp: _FileStamp, *, parent: int | None = None) -> bytes:
    # Refuse a substituted symlink or special file before reading any content.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(_at(path, parent), flags, dir_fd=parent), "rb") as stream:
        if _FileStamp.from_stat(os.fstat(stream.fileno())) != stamp:
            raise ConfigError(f"Pi file changed during preflight: {path}")
        content = stream.read()
        if _FileStamp.from_stat(os.fstat(stream.fileno())) != stamp:
            raise ConfigError(f"Pi file changed during preflight: {path}")
    return content


def _snapshot(
    path: Path, *, read_file: bool = False, parent: int | None = None
) -> _Snapshot:
    stamp = _lstat(path, parent=parent)
    content: FileContent = None
    if stamp is not None:
        if stat.S_ISLNK(stamp.mode):
            content = os.readlink(_at(path, parent), dir_fd=parent)
        elif read_file and stat.S_ISREG(stamp.mode):
            content = _read_file(path, stamp, parent=parent)
        if _lstat(path, parent=parent) != stamp:
            raise ConfigError(f"Pi path changed during preflight: {path}")
    return _Snapshot(stamp, content)


# Read YAML nodes without constructing application objects. Pi uses YAML 1.2
# Core scalar types, so ordinary strings such as "yes" must remain strings.
_PI_YAML: Any = type("_PiYamlLoader", (yaml.BaseLoader,), {})
_PI_YAML.add_implicit_resolver(
    "tag:yaml.org,2002:null",  # Only the distinction from a string matters.
    re.compile(
        r"^(?:~|[Nn]ull|NULL|[Tt]rue|TRUE|[Ff]alse|FALSE|"
        r"0o[0-7]+|0x[0-9a-fA-F]+|"
        r"[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?|"
        r"[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN)|)$"
    ),
    None,
)


def _pi_frontmatter(content: bytes) -> dict[str, str]:
    text = content.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    end = text.find("\n---", 3) if text.startswith("---") else -1
    if end < 0:
        return {}
    document = yaml.compose(text[4:end], Loader=_PI_YAML)
    if not isinstance(document, yaml.MappingNode):
        return {}
    fields: dict[str, str] = {}
    seen: set[str] = set()
    for key, value in document.value:
        if not isinstance(key, yaml.ScalarNode) or key.tag != "tag:yaml.org,2002:str":
            continue
        if key.value in seen:
            raise ValueError(f"Duplicate Pi frontmatter field {key.value!r}")
        seen.add(key.value)
        if (
            key.value in {"name", "description"}
            and isinstance(value, yaml.ScalarNode)
            and value.tag == "tag:yaml.org,2002:str"
        ):
            fields[key.value] = value.value
    return fields


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
        fields = _pi_frontmatter(content)
    except (ValueError, yaml.YAMLError) as exc:
        raise SourceError(
            f"Invalid Pi frontmatter in {bundle / skill_file}: {exc}"
        ) from exc
    if not fields.get("description", "").strip():
        raise SourceError(
            f"Pi skill requires a non-empty description: {bundle / skill_file}"
        )
    return fields.get("name") or bundle.name, digest.hexdigest()


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
) -> tuple[dict[Path, _Skill], dict[str, Path], tuple[str, ...]]:
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
            anchored_path_pattern(destination)  # Verify one literal line.
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
    return skills, names, tuple(dict.fromkeys(skipped))


def _check_unmanaged_skill_names(
    root: Path, names: dict[str, Path], owned: Iterable[Path]
) -> None:
    if not names:
        return
    skills_root = root / _SKILLS
    managed = {root / path for path in owned}

    def read_skill(path: Path) -> bool:
        try:
            source = path.resolve(strict=True)
        except (FileNotFoundError, NotADirectoryError, RuntimeError):
            return False
        stamp = _lstat(source)
        if stamp is None or not stat.S_ISREG(stamp.mode):
            return False
        if path == skills_root / "SKILL.md":
            raise ConfigError(f"Pi skill root shadows managed bundles: {path}")
        try:
            fields = _pi_frontmatter(_read_file(source, stamp))
        except (ValueError, yaml.YAMLError):
            return True  # A present SKILL.md stops Pi's directory descent.
        if fields.get("description", "").strip():
            name = fields.get("name") or path.parent.name
            if name in names:
                raise ConfigError(
                    f"Pi skill name collision {name!r}: {path} conflicts with "
                    f"{names[name]}"
                )
        return True

    def visit(directory: Path, ancestors: frozenset[Path]) -> None:
        try:
            actual = directory.resolve(strict=True)
        except (FileNotFoundError, NotADirectoryError, RuntimeError):
            return
        if actual in ancestors or not actual.is_dir():
            return
        if read_skill(directory / "SKILL.md"):
            return
        for entry in sorted(directory.iterdir()):
            if (
                entry.name.startswith(".")
                or entry.name == "node_modules"
                or entry in managed
            ):
                continue
            if entry.is_dir():
                visit(entry, ancestors | {actual})
            elif directory == skills_root and entry.suffix == ".md":
                read_skill(entry)

    visit(skills_root, frozenset())


def iter_pi_skill_pairs(
    element: Element, project_root: Path, catalog: Path
) -> Iterator[tuple[Path, Path]]:
    """Resolve the complete bundle paths discoverable by native Pi."""
    try:
        skills, _, _ = _collect_skills([element], catalog.resolve())
    except OSError as exc:
        raise SourceError(f"Cannot read Pi catalog {catalog}: {exc}") from exc
    for path, skill in skills.items():
        yield Path(skill.link), project_root / path


def _load_ownership(
    snapshot: _Snapshot,
) -> tuple[dict[Path, _Skill], _HookOwnership | None, PiMcpOwnership | None]:
    if snapshot.stamp is None:
        return {}, None, None
    try:
        if not isinstance(snapshot.content, bytes):
            raise ValueError("expected a regular file")
        raw = json.loads(snapshot.content, object_pairs_hook=unique_json)
        if (
            not isinstance(raw, dict)
            or not {"version", "skills"} <= raw.keys()
            or not raw.keys() <= {"version", "skills", "hooks", "mcp"}
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
        mcp = load_mcp_ownership(raw["mcp"]) if "mcp" in raw else None
        return result, hooks, mcp
    except ValueError as exc:
        raise ConfigError(f"Invalid Pi ownership registry {_OWNERSHIP}: {exc}") from exc


def iter_pi_local_paths(root: Path) -> Iterator[Path]:
    """Yield attested local Pi artefacts, keeping user and shared files visible."""
    pi_dir = _lstat(root / _PI)
    if pi_dir is None or not stat.S_ISDIR(pi_dir.mode):
        return
    registry = _snapshot(root / _OWNERSHIP, read_file=True)
    if registry.stamp is None:
        return
    skills, hooks, mcp = _load_ownership(registry)
    yield _OWNERSHIP
    skills_dir = _lstat(root / _SKILLS)
    if skills_dir is not None and stat.S_ISDIR(skills_dir.mode):
        for path, skill in skills.items():
            if _snapshot(root / path).content == skill.link:
                yield path

    extensions = _lstat(root / _HOOKS.parent)
    if hooks is not None and extensions is not None and stat.S_ISDIR(extensions.mode):
        content = _snapshot(root / _HOOKS, read_file=True).content
        if (
            isinstance(content, bytes)
            and hashlib.sha256(content).hexdigest() == hooks.sha256
        ):
            yield _HOOKS

    if mcp is not None and mcp.created:
        content = _snapshot(root / PI_MCP_PATH, read_file=True).content
        if isinstance(content, bytes) and is_generated_mcp_file(content, mcp):
            yield PI_MCP_PATH


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


def _collect_mcp(packages: Sequence[str], catalog: Path) -> PiMcpPlan | None:
    def read_source(path: Path) -> bytes:
        _source_dir(catalog, path.parent)
        current = _snapshot(path, read_file=True)
        if not isinstance(current.content, bytes):
            raise SourceError(f"Pi requires a regular MCP source file at {path}")
        return current.content

    return collect_pi_mcp(list(packages), catalog, read_source)


def _plan_mcp(
    root: Path,
    mcp: PiMcpPlan | None,
    recorded: PiMcpOwnership | None,
    leaves: dict[Path, _Snapshot],
    changes: list[PiFileChange],
    drift: list[str],
) -> PiMcpOwnership | None:
    if (mcp is None or not mcp.servers) and recorded is None:
        return None

    current = _snapshot(root / PI_MCP_PATH, read_file=True)
    if current.stamp is not None and not isinstance(current.content, bytes):
        raise ConfigError(f"Pi requires a regular MCP config file at {PI_MCP_PATH}")
    leaves[PI_MCP_PATH] = current
    content = current.content if isinstance(current.content, bytes) else None
    updated, ownership, mcp_drift = plan_mcp_update(content, mcp, recorded)
    drift.extend(mcp_drift)
    if updated != content:
        changes.append(PiFileChange(PI_MCP_PATH, current, updated))
    return ownership


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
    recorded, recorded_hooks, recorded_mcp = _load_ownership(registry)
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
    skills, names, skipped = _collect_skills(elements, catalog)
    hooks = _collect_hooks(storage_root, elements)
    mcp = _collect_mcp(packages, catalog) if enabled else None
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

    _check_unmanaged_skill_names(root, names, recorded.keys())
    hook_ownership = _plan_hooks(
        root, hooks, recorded_hooks, parents, leaves, changes, drift
    )
    mcp_ownership = _plan_mcp(root, mcp, recorded_mcp, leaves, changes, drift)
    has_resources = (
        bool(skills) or hook_ownership is not None or mcp_ownership is not None
    )
    if (
        skills != recorded
        or hook_ownership != recorded_hooks
        or mcp_ownership != recorded_mcp
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
        if mcp_ownership is not None:
            updated_ownership["mcp"] = asdict(mcp_ownership)
        updated_registry = (
            _json_bytes(updated_ownership, sort_keys=True) if has_resources else None
        )
        changes.append(PiFileChange(_OWNERSHIP, registry, updated_registry))
        if not drift:
            drift.append(f"{_OWNERSHIP} STALE (no resources remain)")

    resources = set(skills)
    if hooks is not None:
        resources.add(_HOOKS)
    if mcp_ownership is not None:
        resources.add(PI_MCP_PATH)
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
        mcp,
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


def _assert_leaf(
    root: Path, path: Path, expected: _Snapshot, *, parent: int | None = None
) -> None:
    actual = _snapshot(
        root / path, read_file=isinstance(expected.content, bytes), parent=parent
    )
    if actual != expected:
        raise ConfigError(f"Pi destination changed after preflight: {path}")


def _stage(path: Path, content: bytes | str, mode: int, parent: int | None) -> None:
    if isinstance(content, str):
        os.symlink(content, _at(path, parent), target_is_directory=True, dir_fd=parent)
    elif parent is None:
        path.write_bytes(content)
        path.chmod(stat.S_IMODE(mode))
    else:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(_at(path, parent), flags, mode, dir_fd=parent)
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(fd, stat.S_IMODE(mode))
            stream.write(content)


def _stage_change(
    directory: Path, parent: int | None, index: int, change: PiFileChange
) -> tuple[Path, _Snapshot | None]:
    after = directory / f"{index}.new"
    if change.after is None:
        return after, None
    mode = change.before.stamp.mode if change.before.stamp is not None else 0o600
    _stage(after, change.after, mode, parent)
    return after, _snapshot(
        after, read_file=isinstance(change.after, bytes), parent=parent
    )


@dataclass
class _Publication:
    path: Path
    parent: int | None
    held: Path | None = None
    written: _Snapshot | None = None
    published: bool = False


def _move_leaf(
    source: Path,
    destination: Path,
    *,
    source_fd: int | None = None,
    destination_fd: int | None = None,
) -> None:
    os.replace(
        _at(source, source_fd),
        _at(destination, destination_fd),
        src_dir_fd=source_fd,
        dst_dir_fd=destination_fd,
    )


def _publish_new(
    source: Path,
    destination: Path,
    *,
    source_fd: int | None = None,
    destination_fd: int | None = None,
) -> None:
    """Publish exactly one leaf, failing when the name is already occupied."""
    if os.name == "nt":
        source.rename(destination)
    else:
        os.link(
            _at(source, source_fd),
            _at(destination, destination_fd),
            src_dir_fd=source_fd,
            dst_dir_fd=destination_fd,
            follow_symlinks=False,
        )


def _matches_captured(
    path: Path, expected: _Snapshot, parent: int | None = None
) -> bool:
    actual = _snapshot(
        path, read_file=isinstance(expected.content, bytes), parent=parent
    )
    before, current = expected.stamp, actual.stamp
    # Moving or linking a leaf can change ctime without changing its data.
    return (
        before is not None
        and current is not None
        and actual.content == expected.content
        and before.identity() == current.identity()
        and before.modified == current.modified
        and before.size == current.size
    )


def _undo_publication(
    entry: _Publication,
    destination: Path,
    reverted: Path,
    stage_fd: int | None,
    recover: set[Path],
) -> None:
    if entry.written is not None and (
        entry.published or _matches_captured(destination, entry.written, entry.parent)
    ):
        # Record custody before the syscall in case it is interrupted.
        recover.add(reverted)
        _move_leaf(
            destination, reverted, source_fd=entry.parent, destination_fd=stage_fd
        )
        if not _matches_captured(reverted, entry.written, stage_fd):
            _publish_new(
                reverted, destination, source_fd=stage_fd, destination_fd=entry.parent
            )
            recover.discard(reverted)
            raise ConfigError("changed since publication")
        recover.discard(reverted)
    if entry.held is not None:
        if _lstat(entry.held, parent=stage_fd) is not None:
            _publish_new(
                entry.held, destination, source_fd=stage_fd, destination_fd=entry.parent
            )
        recover.discard(entry.held)


def _dir_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _verify_directory(path: Path, stamp: _FileStamp | None, fd: int | None) -> None:
    current = _FileStamp.from_stat(os.fstat(fd)) if fd is not None else _lstat(path)
    if stamp is None or current is None or stamp.identity() != current.identity():
        raise ConfigError(f"Pi destination directory changed after preflight: {path}")


@contextmanager
def _pin_windows_directory(path: Path) -> Iterator[None]:
    # A Windows directory handle opened without FILE_SHARE_DELETE prevents rename
    # while absolute path operations use the pinned, non-reparse directory.
    import ctypes
    from ctypes import wintypes

    if sys.platform != "win32":
        raise ConfigError("Windows directory pinning requires Windows")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    open_dir = api.CreateFileW
    open_dir.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    open_dir.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    open_existing = 3
    directory_no_follow = (
        0x02000000 | 0x00200000
    )  # Backup semantics and open reparse point.
    handle = open_dir(str(path), 1, 3, None, open_existing, directory_no_follow, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError()
    try:
        if path.is_symlink() or path.is_junction():
            raise ConfigError(f"Pi requires a real directory at {path}")
        yield
    finally:
        api.CloseHandle(handle)


def _destination_parent(
    root: Path,
    path: Path,
    parents: dict[Path, _FileStamp | None],
    opened: dict[Path, int | None],
    handles: ExitStack,
    created: list[Path] | None,
) -> int | None:
    for relative in reversed(path.parents):
        if relative in opened:
            continue
        directory = root / relative
        parent = opened[relative.parent]
        stamp = parents[relative]
        if stamp is None and created is not None:
            os.mkdir(_at(directory, parent), dir_fd=parent)
            created.append(relative)
            stamp = _lstat(directory, parent=parent)
            _real_dir(directory, stamp)
            parents[relative] = stamp
        if parent is None:
            handles.enter_context(_pin_windows_directory(directory))
            fd = None
        else:
            fd = os.open(directory.name, _dir_flags(), dir_fd=parent)
            handles.callback(os.close, fd)
        _verify_directory(directory, stamp, fd)
        opened[relative] = fd
    return opened[path.parent]


def _transaction_directory(
    root: Path, project_fd: int | None
) -> tuple[Path, int | None]:
    if project_fd is None:
        return Path(tempfile.mkdtemp(prefix=".ai-dotfiles-pi-", dir=root)), None
    name = f".ai-dotfiles-pi-{secrets.token_hex(12)}"
    os.mkdir(name, 0o700, dir_fd=project_fd)
    return root / name, os.open(name, _dir_flags(), dir_fd=project_fd)


def _apply_changes(
    plan: PiPlan, changes: list[PiFileChange], project_fd: int | None
) -> None:
    parents = plan.parents.copy()
    _verify_directory(plan.root, parents[Path(".")], project_fd)
    opened = {Path("."): project_fd}
    created: list[Path] = []
    # The transaction directory is outside the Pi discovery trees.
    directory, stage_fd = _transaction_directory(plan.root, project_fd)
    recover: set[Path] = set()
    cleanup = False
    applied: list[_Publication] = []
    originals: list[tuple[Path, PiFileChange]] = []
    handles = ExitStack()
    try:
        _stage(directory / ".gitignore", b"*\n", 0o600, stage_fd)
        staged = [
            _stage_change(directory, stage_fd, index, change)
            for index, change in enumerate(changes)
        ]
        for index, (change, (after, written)) in enumerate(
            zip(changes, staged, strict=True)
        ):
            parent = _destination_parent(
                plan.root,
                change.path,
                parents,
                opened,
                handles,
                created if written is not None else None,
            )
            _assert_parents(plan.root, change.path, parents)
            _assert_leaf(plan.root, change.path, change.before, parent=parent)
            destination = plan.root / change.path
            entry = _Publication(change.path, parent, written=written)
            applied.append(entry)
            if change.before.stamp is not None:
                held = directory / f"{index}.old"
                entry.held = held
                recover.add(held)
                _move_leaf(destination, held, source_fd=parent, destination_fd=stage_fd)
                if not _matches_captured(held, change.before, stage_fd):
                    raise ConfigError(
                        f"Pi destination changed at publication: {change.path}"
                    )
                originals.append((held, change))
            if written is not None:
                _publish_new(
                    after, destination, source_fd=stage_fd, destination_fd=parent
                )
                entry.published = True
            _assert_parents(plan.root, change.path, parents)

        for held, change in originals:
            if not _matches_captured(held, change.before, stage_fd):
                raise ConfigError(
                    f"Pi destination changed during publication: {change.path}"
                )
        # A parent may change after the last write to that particular directory.
        for parent_path in opened:
            _assert_parents(plan.root, parent_path / "child", parents)
        cleanup = True
    except (AiDotfilesError, OSError, KeyboardInterrupt) as exc:
        failed: list[str] = []
        for index, entry in enumerate(reversed(applied)):
            try:
                _undo_publication(
                    entry,
                    plan.root / entry.path,
                    directory / f"{index}.undo",
                    stage_fd,
                    recover,
                )
            except (AiDotfilesError, OSError) as rollback_error:
                failed.append(f"{entry.path}: {rollback_error}")

        # On Windows release child handles before removing our empty directories.
        if project_fd is None:
            handles.close()
        for path in reversed(created):
            try:
                parent = opened[path.parent]
                captured = _lstat(plan.root / path, parent=parent)
                expected = parents[path]
                if (
                    captured is None
                    or expected is None
                    or captured.identity() != expected.identity()
                ):
                    raise ConfigError("directory changed since creation")
                os.rmdir(_at(plan.root / path, parent), dir_fd=parent)
            except (AiDotfilesError, OSError) as rollback_error:
                failed.append(f"{path}: {rollback_error}")
        suffix = f"; rollback incomplete ({'; '.join(failed)})" if failed else ""
        if recover:
            suffix += f"; files retained at {directory}"
        cleanup = not recover
        if isinstance(exc, KeyboardInterrupt) and not suffix:
            raise
        message = (
            "Pi transaction interrupted"
            if isinstance(exc, KeyboardInterrupt)
            else str(exc)
        )
        raise LinkError(f"{message}{suffix}") from exc
    finally:
        handles.close()
        if stage_fd is not None:
            os.close(stage_fd)
        # An unexpected exception or an interrupted rollback leaves custody intact.
        if cleanup:
            shutil.rmtree(_at(directory, project_fd), dir_fd=project_fd)


@contextmanager
def _project_write_lock(root: Path) -> Iterator[int | None]:
    """Serialize POSIX commits and pin the project root for native operations."""
    if os.name == "nt":
        with _pin_windows_directory(root):
            yield None
        return

    import fcntl

    fd = os.open(root, _dir_flags())
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield fd
    finally:
        os.close(fd)


def _commit_plan(
    plan: PiPlan,
    manifest_path: Path,
    manifest_change: Sequence[str] | None,
    project_fd: int | None,
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
        # The legacy text-mode writer emits native line endings.
        if (
            not isinstance(current.content, bytes)
            or current.content.replace(b"\r\n", b"\n") != plan.updated_manifest
        ):
            raise ConfigError(f"Pi manifest changed after preflight: {manifest_path}")
    else:
        _assert_leaf(plan.root, manifest_path, plan.initial_manifest)
    for path, expected in plan.leaves.items():
        _assert_parents(plan.root, path, plan.parents)
        _assert_leaf(plan.root, path, expected)
    if plan.enabled and changes:
        elements = parse_elements(list(plan.packages))
        skills, names, _ = _collect_skills(elements, plan.catalog)
        if skills != plan.skills:
            raise ConfigError("Pi skill sources changed after preflight")
        _check_unmanaged_skill_names(plan.root, names, plan.leaves.keys())
        if _collect_hooks(plan.storage_root, elements) != plan.hooks:
            raise ConfigError("Pi hook sources changed after preflight")
        if _collect_mcp(plan.packages, plan.catalog) != plan.mcp:
            raise ConfigError("Pi MCP sources changed after preflight")
    if changes:
        _apply_changes(plan, changes, project_fd)
    return changes


def apply_pi_project(
    plan: PiPlan,
    *,
    manifest_change: Sequence[str] | None = None,
) -> PiReport:
    """Publish the plan, committing a Pi-only package change as the last file."""
    manifest_path = project_manifest_path(plan.root).relative_to(plan.root)
    try:
        with _project_write_lock(plan.root) as project_fd:
            changes = _commit_plan(plan, manifest_path, manifest_change, project_fd)
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

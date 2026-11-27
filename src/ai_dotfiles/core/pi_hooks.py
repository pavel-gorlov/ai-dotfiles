"""Compile the supported catalog hooks into a project-local Pi extension."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from ai_dotfiles.core.errors import SourceError

PI_HOOK_GENERATOR_VERSION = 1


@dataclass(frozen=True)
class _Handler:
    id: str
    domain: str
    phase: str
    matcher: str
    command: str
    script: str
    command_family: str | None = None


_CLAUDE_HOOKS = "$CLAUDE_PROJECT_DIR/.claude/hooks/"
_HANDLERS = (
    _Handler(
        "route-to-agent-git",
        "gitflow",
        "PreToolUse",
        "Bash",
        _CLAUDE_HOOKS + "route-to-agent.sh",
        "route-to-agent.sh",
        "git",
    ),
    _Handler(
        "route-to-agent-gh",
        "gitflow",
        "PreToolUse",
        "Bash",
        _CLAUDE_HOOKS + "route-to-agent.sh",
        "route-to-agent.sh",
        "gh",
    ),
    _Handler(
        "tm-collision-check",
        "taskmanager",
        "PreToolUse",
        "Bash",
        "tm-hook collision-check",
        "tm-collision-check.sh",
    ),
    _Handler(
        "pr-review-nudge",
        "gitflow",
        "PostToolUse",
        "Bash",
        _CLAUDE_HOOKS + "pr-review-nudge.sh",
        "pr-review-nudge.sh",
    ),
    _Handler(
        "tm-mirror-push",
        "taskmanager",
        "PostToolUse",
        "Edit|Write",
        "tm-hook mirror-push",
        "tm-mirror-push",
    ),
)


@dataclass(frozen=True)
class PiHookPlan:
    content: bytes
    fingerprint: str


def _read_source(catalog: Path, path: Path) -> tuple[int, bytes]:
    try:
        for parent in reversed(path.relative_to(catalog).parents):
            if not stat.S_ISDIR((catalog / parent).lstat().st_mode):
                raise SourceError(
                    f"Pi requires a real hook source directory at {catalog / parent}"
                )
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise SourceError(f"Pi requires a regular hook source file at {path}")
        flags = (
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        with os.fdopen(os.open(path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (
                opened.st_dev,
                opened.st_ino,
            ):
                raise SourceError(f"Pi hook source changed during preflight: {path}")
            content = stream.read()
            after = os.fstat(stream.fileno())
        if (before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) or path.lstat() != after:
            raise SourceError(f"Pi hook source changed during preflight: {path}")
    except OSError as exc:
        raise SourceError(f"Cannot read Pi hook source {path}: {exc}") from exc
    return stat.S_IMODE(after.st_mode), content


def _check_entry(data: object, path: Path, handler: _Handler) -> None:
    hooks = data.get("hooks") if isinstance(data, dict) else None
    groups = hooks.get(handler.phase) if isinstance(hooks, dict) else None
    expected = {
        "type": "command",
        "command": handler.command,
    }
    if handler.command_family is not None:
        expected["if"] = f"Bash({handler.command_family} *)"
    matches = 0
    if isinstance(groups, list):
        for group in groups:
            if (
                isinstance(group, dict)
                and group.get("matcher") == handler.matcher
                and isinstance(group.get("hooks"), list)
            ):
                matches += group["hooks"].count(expected)
    if matches != 1:
        raise SourceError(
            f"Expected exactly one supported Pi hook {handler.id} in {path}"
        )


def collect_pi_hooks(storage_root: Path, domains: Iterable[str]) -> PiHookPlan | None:
    """Validate and fingerprint the selected handlers and render their extension."""
    selected = set(domains)
    handlers = [handler for handler in _HANDLERS if handler.domain in selected]
    if not handlers:
        return None

    catalog = (storage_root / "catalog").resolve()
    digest = hashlib.sha256()
    fragments: dict[Path, object] = {}
    scripts: set[Path] = set()
    config: list[dict[str, object]] = []

    def read_source(path: Path) -> bytes:
        mode, content = _read_source(catalog, path)
        for field in (
            os.fsencode(path.relative_to(catalog)),
            str(mode).encode(),
            content,
        ):
            digest.update(len(field).to_bytes(8, "big"))
            digest.update(field)
        return content

    for handler in handlers:
        domain = catalog / handler.domain
        fragment = domain / "settings.fragment.json"
        if fragment not in fragments:
            try:
                fragments[fragment] = json.loads(read_source(fragment))
            except ValueError as exc:
                raise SourceError(
                    f"Invalid Pi hook fragment {fragment}: {exc}"
                ) from exc
        _check_entry(fragments[fragment], fragment, handler)
        script = domain / "hooks" / handler.script
        if script not in scripts:
            read_source(script)
            scripts.add(script)
        config.append(
            {
                "id": handler.id,
                "phase": handler.phase,
                "tools": handler.matcher.lower().split("|"),
                "commandFamily": handler.command_family,
                "script": str(script),
            }
        )

    template = resources.files("ai_dotfiles.scaffold.templates").joinpath("pi_hooks.js")
    try:
        body = template.read_bytes()
    except OSError as exc:
        raise SourceError(f"Cannot read packaged Pi hook template: {exc}") from exc
    header = (
        f"// Generated by ai-dotfiles, version {PI_HOOK_GENERATOR_VERSION}.\n"
        f"const handlers = {json.dumps(config, indent=2)};\n\n"
    )
    return PiHookPlan(header.encode() + body, digest.hexdigest())

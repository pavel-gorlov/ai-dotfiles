"""Translate domain hooks into a Codex project ``.codex/hooks.json``.

Codex CLI (2026) has a lifecycle hook harness whose event vocabulary and
matcher+command handler shape mirror Claude Code's almost 1:1 — verified
against the real ``~/.codex/hooks.json`` a Codex install writes. So a domain's
``settings.fragment.json`` ``hooks`` (which the Claude target merges into
``settings.json``) can be emitted for Codex too, closing the gap the earlier
fail-loud skip left.

The translation is deliberately conservative:

* only events with a Codex twin (:data:`CODEX_HOOK_EVENTS`) are emitted; the
  rest (``Notification``, ``SessionEnd`` …) are reported as skipped;
* each group keeps its ``matcher``; each handler keeps ``type`` / ``command``
  / ``timeout``. Claude's per-handler ``if`` condition (a command-glob guard,
  e.g. ``Bash(git *)``) has **no** Codex equivalent — Codex matches on the
  tool *name* via ``matcher`` — so it is dropped. The guard script itself
  should self-filter (the ``if`` was a Claude-side optimisation);
* ``$CLAUDE_PROJECT_DIR`` in a command is rewritten to
  :data:`_CODEX_PROJECT_VAR`. The referenced scripts live in ``.claude/hooks/``
  (materialised for the Claude target), so a Codex-only project must also keep
  those scripts available.

``.codex/hooks.json`` is a shared file (a user may hand-author project hooks,
and it coexists with the user-level ``~/.codex/hooks.json`` Codex merges
additively). Ownership is tracked by per-group signature in a sidecar so a
later :func:`strip_codex_hooks` removes only domain-contributed groups and
leaves the user's intact — the same discipline as the MCP writer.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ai_dotfiles.core.errors import ConfigError, LinkError
from ai_dotfiles.core.settings_merge import load_fragment

__all__ = [
    "CODEX_HOOK_EVENTS",
    "HOOKS_FILENAME",
    "HooksResult",
    "build_codex_hooks",
    "hooks_path",
    "strip_codex_hooks",
    "translate_hooks",
    "write_codex_hooks",
]

HOOKS_FILENAME = "hooks.json"
_OWNERSHIP_FILENAME = ".ai-dotfiles-hooks-ownership.json"

# Codex lifecycle events with a Claude Code twin. Events with no twin are
# reported as skipped rather than emitted.
CODEX_HOOK_EVENTS: frozenset[str] = frozenset(
    {
        "PreToolUse",
        "PostToolUse",
        "PermissionRequest",
        "SessionStart",
        "Stop",
        "UserPromptSubmit",
        "SubagentStart",
        "SubagentStop",
        "PreCompact",
    }
)

# Claude's project-root variable and the Codex substitute used in hook
# commands. NOTE: isolated here so it is a one-line change if a Codex version
# names its project-root variable differently.
_CLAUDE_PROJECT_VAR = "$CLAUDE_PROJECT_DIR"
_CODEX_PROJECT_VAR = "$CODEX_PROJECT_DIR"


class HooksResult:
    """Outcome of a Codex ``hooks.json`` write.

    ``status`` is ``"created"`` / ``"updated"`` / ``"removed"``.
    ``skipped_events`` maps a domain name to the hook events it declared that
    have no Codex twin — the command layer turns this into an explicit note.
    """

    __slots__ = ("skipped_events", "status")

    def __init__(
        self, status: str, skipped_events: dict[str, list[str]] | None = None
    ) -> None:
        self.status = status
        self.skipped_events: dict[str, list[str]] = skipped_events or {}

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HooksResult):
            return NotImplemented
        return (
            self.status == other.status and self.skipped_events == other.skipped_events
        )

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return (
            f"HooksResult(status={self.status!r}, "
            f"skipped_events={self.skipped_events!r})"
        )


def hooks_path(codex_dir: Path) -> Path:
    """Return the Codex hooks path inside ``codex_dir``.

    ``codex_dir`` is the directory holding ``hooks.json`` — project
    scope passes ``<root>/.codex``, the global scope ``$CODEX_HOME``.
    """
    return codex_dir / HOOKS_FILENAME


def _ownership_path(codex_dir: Path) -> Path:
    return codex_dir / _OWNERSHIP_FILENAME


def _translate_handler(handler: dict[str, Any]) -> dict[str, Any] | None:
    """Translate one Claude hook handler to a Codex one, or ``None`` to drop it.

    Keeps ``type``/``command``/``timeout``; drops the Claude-only ``if``
    guard; rewrites ``$CLAUDE_PROJECT_DIR`` in the command.
    """
    if handler.get("type") != "command":
        return None
    command = handler.get("command")
    if not isinstance(command, str) or not command:
        return None
    out: dict[str, Any] = {
        "type": "command",
        "command": command.replace(_CLAUDE_PROJECT_VAR, _CODEX_PROJECT_VAR),
    }
    timeout = handler.get("timeout")
    if isinstance(timeout, int | float) and not isinstance(timeout, bool):
        out["timeout"] = timeout
    return out


def _translate_group(group: dict[str, Any]) -> dict[str, Any] | None:
    handlers = group.get("hooks")
    if not isinstance(handlers, list):
        return None
    translated = [
        t
        for h in handlers
        if isinstance(h, dict) and (t := _translate_handler(h)) is not None
    ]
    if not translated:
        return None
    out: dict[str, Any] = {}
    matcher = group.get("matcher")
    if isinstance(matcher, str) and matcher:
        out["matcher"] = matcher
    out["hooks"] = translated
    return out


def translate_hooks(
    claude_hooks: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Translate a Claude ``hooks`` dict to Codex form.

    Returns ``(codex_hooks, skipped_events)`` — ``codex_hooks`` maps each
    twin event to its translated groups; ``skipped_events`` lists events with
    no Codex twin that were dropped.
    """
    codex: dict[str, list[dict[str, Any]]] = {}
    skipped: list[str] = []
    for event, groups in claude_hooks.items():
        if event not in CODEX_HOOK_EVENTS:
            skipped.append(event)
            continue
        if not isinstance(groups, list):
            continue
        translated = [
            g
            for grp in groups
            if isinstance(grp, dict) and (g := _translate_group(grp)) is not None
        ]
        if translated:
            codex.setdefault(event, []).extend(translated)
    return codex, skipped


def build_codex_hooks(
    fragment_paths: list[tuple[str, Path]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[str]]]:
    """Assemble Codex hooks from every domain ``settings.fragment.json``.

    ``fragment_paths`` is ``(domain_name, fragment_path)`` in topological
    order. Returns ``(codex_hooks, skipped_by_domain)``.
    """
    codex: dict[str, list[dict[str, Any]]] = {}
    skipped_by_domain: dict[str, list[str]] = {}
    for domain_name, path in fragment_paths:
        fragment = load_fragment(path)
        hooks = fragment.get("hooks")
        if not isinstance(hooks, dict):
            continue
        translated, skipped = translate_hooks(hooks)
        for event, groups in translated.items():
            codex.setdefault(event, []).extend(groups)
        if skipped:
            skipped_by_domain[domain_name] = skipped
    return codex, skipped_by_domain


def _group_signature(event: str, group: dict[str, Any]) -> str:
    payload = json.dumps([event, group], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_hooks_file(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
    hooks = data.get("hooks") if isinstance(data, dict) else None
    return hooks if isinstance(hooks, dict) else {}


def _load_ownership(codex_dir: Path) -> set[str]:
    path = _ownership_path(codex_dir)
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return set(data) if isinstance(data, list) else set()


def _save_ownership(codex_dir: Path, signatures: set[str]) -> None:
    path = _ownership_path(codex_dir)
    if not signatures:
        _delete_ownership(codex_dir)
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(sorted(signatures), indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        raise LinkError(f"Failed to write hooks ownership {path}: {exc}") from exc


def _delete_ownership(codex_dir: Path) -> None:
    try:
        _ownership_path(codex_dir).unlink()
    except FileNotFoundError:
        return
    except OSError as exc:  # pragma: no cover - unreadable sidecar
        raise LinkError(f"Failed to delete hooks ownership: {exc}") from exc


def _write_hooks_file(path: Path, hooks: dict[str, list[dict[str, Any]]]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"hooks": hooks}, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise LinkError(f"Failed to write Codex hooks {path}: {exc}") from exc


def write_codex_hooks(
    codex_dir: Path, fragment_paths: list[tuple[str, Path]]
) -> HooksResult:
    """Emit domain hooks into ``.codex/hooks.json``, preserving user hooks.

    Domain-contributed groups are (re)written; user-authored groups (those
    whose signature is not in the ownership sidecar) survive. When no domain
    declares a translatable hook the domain groups are stripped; a file left
    empty is deleted.

    Raises:
        ConfigError: if an existing ``hooks.json`` is malformed.
        LinkError: if the file cannot be written.
    """
    domain_hooks, skipped_by_domain = build_codex_hooks(fragment_paths)
    path = hooks_path(codex_dir)
    existing_hooks = _load_hooks_file(path)
    prev_sigs = _load_ownership(codex_dir)

    result_hooks: dict[str, list[dict[str, Any]]] = {}
    for event, groups in existing_hooks.items():
        if not isinstance(groups, list):
            continue
        kept = [g for g in groups if _group_signature(event, g) not in prev_sigs]
        if kept:
            result_hooks[event] = kept

    new_sigs: set[str] = set()
    for event, groups in domain_hooks.items():
        for group in groups:
            result_hooks.setdefault(event, []).append(group)
            new_sigs.add(_group_signature(event, group))

    existed = path.is_file()
    try:
        if result_hooks:
            _write_hooks_file(path, result_hooks)
        elif existed:
            path.unlink()
    except OSError as exc:
        raise LinkError(f"Failed to write Codex hooks {path}: {exc}") from exc
    _save_ownership(codex_dir, new_sigs)

    if not new_sigs:
        status = "removed" if prev_sigs else "updated"
    elif not prev_sigs:
        status = "created"
    else:
        status = "updated"
    return HooksResult(status, skipped_by_domain)


def strip_codex_hooks(codex_dir: Path) -> bool:
    """Remove only domain-owned groups from ``.codex/hooks.json``.

    User-authored groups survive; a file left empty is deleted. Returns
    ``True`` if the file was rewritten or deleted, ``False`` if there was
    nothing to strip.
    """
    prev_sigs = _load_ownership(codex_dir)
    path = hooks_path(codex_dir)
    if not path.is_file() or not prev_sigs:
        _delete_ownership(codex_dir)
        return False

    existing_hooks = _load_hooks_file(path)
    surviving: dict[str, list[dict[str, Any]]] = {}
    for event, groups in existing_hooks.items():
        if not isinstance(groups, list):
            continue
        kept = [g for g in groups if _group_signature(event, g) not in prev_sigs]
        if kept:
            surviving[event] = kept

    try:
        if surviving:
            _write_hooks_file(path, surviving)
        else:
            path.unlink()
    except OSError as exc:
        raise LinkError(f"Failed to strip Codex hooks {path}: {exc}") from exc
    _delete_ownership(codex_dir)
    return True

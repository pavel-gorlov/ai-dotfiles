"""Translate Claude permission lists into a Codex exec-policy ``.rules`` file.

Claude gates shell commands with glob-ish entries in ``settings.json``
``permissions`` (``Bash(git fetch:*)``). Codex 0.147 gates them with an
**exec policy**: Starlark ``.rules`` files scanned from a ``rules/``
directory per config layer — ``$CODEX_HOME/rules/`` at user scope,
``<repo>/.codex/rules/`` at project scope (the project layer loads only
once the project is trusted, the same caveat as ``.codex/config.toml``).

ADR ai-1-5 predates that engine and assumed Codex had no per-command
permission model, so the catalog lists were parked in an inert
``[ai_dotfiles.permissions]`` table nothing reads. This module is the
real translation.

Rule shape::

    prefix_rule(
        pattern = ["git", "fetch"],
        decision = "allow",
        justification = "ai-dotfiles: Bash(git fetch:*)",
    )

``decision`` is one of ``allow`` / ``prompt`` / ``forbidden``; layers
merge by *most restrictive* (forbidden > prompt > allow).

What does **not** translate
---------------------------
``prefix_rule`` matches a token prefix, so it is strictly wider than an
exact command. ``Bash(pg_isready)`` authorises exactly that command,
while ``pattern = ["pg_isready"]`` would authorise it with any argument
list. Turning one into the other silently hands out permissions the user
never granted, so entries that cannot be expressed faithfully are
**skipped and reported**, never approximated:

* an exact command with no trailing wildcard — would widen to a prefix;
* an argument list carrying shell syntax (quotes, pipes, redirects,
  substitutions) — the token model cannot express it, and dropping the
  syntax would widen it drastically;
* a wildcard anywhere but the end — no token equivalent;
* a non-``Bash`` tool (``Read()``, ``WebFetch()``, ``mcp__*``) — the exec
  policy governs command execution only.

Ownership
---------
Codex writes the approvals you grant in its TUI to
``rules/default.rules``. ai-dotfiles never touches that file: it owns
exactly the file named here, and the loader scans every ``*.rules`` in
the directory (verified against Codex 0.147), so the two coexist.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_dotfiles.core.codex_config import build_managed_table
from ai_dotfiles.core.errors import LinkError

__all__ = [
    "LOCAL_RULES_FILENAME",
    "MANAGED_HEADER",
    "RULES_FILENAME",
    "PrefixRule",
    "SkippedPermission",
    "catalog_rule_keys",
    "local_rules_path",
    "render_rules",
    "rules_path",
    "rules_state",
    "strip_codex_rules",
    "translate_entry",
    "translate_permissions",
    "write_codex_rules",
    "write_local_codex_rules",
]

# The file ai-dotfiles owns inside ``<codex_dir>/rules/``. Deliberately
# *not* ``default.rules`` — that one is Codex's own, rewritten whenever
# the user approves a command in the TUI.
RULES_FILENAME = "ai-dotfiles.rules"

# The catalog-derived rules (``install``) and the project's own
# hand-authored ones (``migrate``) are kept in separate files: they have
# different lifecycles, and `install --prune` must not consider the local
# one orphaned. Codex scans every ``*.rules`` in the directory.
LOCAL_RULES_FILENAME = "ai-dotfiles-local.rules"

MANAGED_HEADER = "# managed-by: ai-dotfiles"

# Claude permission list -> Codex exec-policy decision.
_DECISIONS: dict[str, str] = {
    "allow": "allow",
    "deny": "forbidden",
    "ask": "prompt",
}

# ``Tool(argument)`` — the Claude permission entry shape.
_ENTRY_RE = re.compile(r"\A(?P<tool>[A-Za-z_][\w]*)\((?P<arg>.*)\)\Z", re.DOTALL)

# Any of these in the argument means the entry describes a *specific*
# invocation (quoting, piping, redirection, substitution), not a command
# prefix. Translating it would discard the constraint and widen the grant.
_SHELL_SYNTAX = set("\"'|&;<>`$()[]{}\\\n")


@dataclass(frozen=True)
class PrefixRule:
    """One translated ``prefix_rule`` entry."""

    pattern: tuple[str, ...]
    decision: str
    source: str


@dataclass(frozen=True)
class SkippedPermission:
    """A permission entry with no faithful exec-policy equivalent."""

    entry: str
    reason: str


def rules_path(codex_dir: Path) -> Path:
    """Return the path of the ai-dotfiles-owned ``.rules`` file."""
    return codex_dir / "rules" / RULES_FILENAME


def translate_entry(entry: str, decision: str) -> PrefixRule | SkippedPermission:
    """Translate one Claude permission entry into a ``prefix_rule``.

    Returns a :class:`SkippedPermission` — never a widened rule — when the
    entry cannot be expressed as a token prefix. See the module docstring
    for why approximating is not an option.
    """
    text = entry.strip()
    match = _ENTRY_RE.match(text)
    if match is None:
        return SkippedPermission(entry, "not a Tool(argument) permission entry")

    tool = match.group("tool")
    if tool != "Bash":
        return SkippedPermission(
            entry, f"the Codex exec policy governs commands only, not {tool}()"
        )

    argument = match.group("arg").strip()
    if not argument:
        return SkippedPermission(entry, "empty command")

    if _SHELL_SYNTAX & set(argument):
        return SkippedPermission(
            entry,
            "argument carries shell syntax a token pattern cannot express",
        )

    # A trailing ``:*`` or ` *` is Claude's "and any arguments" marker —
    # exactly prefix semantics. Anything else is an exact command.
    if "*" not in argument:
        return SkippedPermission(
            entry,
            "exact command — a prefix rule would also allow extra arguments",
        )

    head = argument[:-2] if argument.endswith(":*") else argument[:-1]
    if not argument.endswith("*") or "*" in head:
        return SkippedPermission(entry, "wildcard inside the command, not at the end")

    tokens = tuple(head.split())
    if not tokens:
        return SkippedPermission(entry, "wildcard-only entry matches every command")

    return PrefixRule(tokens, decision, entry)


def translate_permissions(
    permissions: dict[str, Any],
) -> tuple[list[PrefixRule], list[SkippedPermission]]:
    """Translate a Claude ``permissions`` object into exec-policy rules.

    Reads the ``allow`` / ``deny`` / ``ask`` lists and maps each to its
    Codex decision. Rules are de-duplicated on (pattern, decision) and
    returned in deterministic order; skips keep their input order so the
    report reads like the source file.
    """
    rules: dict[tuple[tuple[str, ...], str], PrefixRule] = {}
    skipped: list[SkippedPermission] = []

    for key, decision in _DECISIONS.items():
        entries = permissions.get(key)
        if not isinstance(entries, list):
            continue
        for raw in entries:
            if not isinstance(raw, str):
                continue
            result = translate_entry(raw, decision)
            if isinstance(result, SkippedPermission):
                skipped.append(result)
            else:
                rules.setdefault((result.pattern, result.decision), result)

    ordered = sorted(rules.values(), key=lambda r: (r.pattern, r.decision))
    return ordered, skipped


def render_rules(rules: list[PrefixRule]) -> str:
    """Render ``rules`` as the body of a Starlark ``.rules`` file.

    Returns an empty string when there is nothing to write, so the caller
    can delete the file rather than leave an empty one behind.
    """
    if not rules:
        return ""

    lines = [
        MANAGED_HEADER,
        "# Generated from Claude permission lists — do not edit by hand.",
        "# Regenerate with `ai-dotfiles install` (or `reconcile`).",
        "",
    ]
    for rule in rules:
        pattern = ", ".join(json.dumps(token) for token in rule.pattern)
        lines += [
            "prefix_rule(",
            f"    pattern = [{pattern}],",
            f"    decision = {json.dumps(rule.decision)},",
            # Codex echoes the justification verbatim when it rejects a
            # command, so naming the source entry makes a block traceable
            # back to the catalog line that caused it.
            f"    justification = {json.dumps('ai-dotfiles: ' + rule.source)},",
            ")",
            "",
        ]
    return "\n".join(lines)


def _expected_text(
    fragment_paths: list[tuple[str, Path]]
) -> tuple[str, list[PrefixRule], list[SkippedPermission]]:
    """Compute the file content the current fragments should produce."""
    managed, _ = build_managed_table(fragment_paths)
    permissions = managed.get("permissions")
    if not isinstance(permissions, dict):
        return "", [], []
    rules, skipped = translate_permissions(permissions)
    return render_rules(rules), rules, skipped


def write_codex_rules(
    codex_dir: Path,
    fragment_paths: list[tuple[str, Path]],
) -> tuple[str, list[SkippedPermission]]:
    """Write the ai-dotfiles-owned ``.rules`` file from domain fragments.

    Returns ``(status, skipped)`` where status is ``created`` / ``updated``
    / ``removed`` / ``unchanged``, and ``skipped`` lists the permission
    entries with no faithful exec-policy equivalent so the command layer
    can report them.

    Raises:
        LinkError: if the file cannot be written or removed.
    """
    path = rules_path(codex_dir)
    existed = path.is_file()
    text, _, skipped = _expected_text(fragment_paths)

    try:
        if not text:
            if existed:
                path.unlink()
                return "removed", skipped
            return "unchanged", skipped
        if existed and path.read_text(encoding="utf-8") == text:
            return "unchanged", skipped
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise LinkError(f"Failed to write Codex rules {path}: {exc}") from exc

    return ("updated" if existed else "created"), skipped


def rules_state(codex_dir: Path, fragment_paths: list[tuple[str, Path]]) -> str:
    """Return the drift state of the managed ``.rules`` file.

    Like ``config.toml``, the file carries no source digest — it is wholly
    ai-dotfiles-owned, so drift is detected by recomputing the expected
    content from the current fragments and comparing. Returns ``absent``
    (nothing expected, nothing on disk), ``missing``, ``stale`` or ``ok``.
    """
    path = rules_path(codex_dir)
    expected, _, _ = _expected_text(fragment_paths)
    if not expected:
        return "stale" if path.is_file() else "absent"
    if not path.is_file():
        return "missing"
    try:
        current = path.read_text(encoding="utf-8")
    except OSError:
        return "stale"
    return "ok" if current == expected else "stale"


def local_rules_path(codex_dir: Path) -> Path:
    """Return the path of the ``migrate``-owned local ``.rules`` file."""
    return codex_dir / "rules" / LOCAL_RULES_FILENAME


def catalog_rule_keys(
    fragment_paths: list[tuple[str, Path]],
) -> set[tuple[tuple[str, ...], str]]:
    """Return the (pattern, decision) keys the catalog fragments produce.

    ``migrate`` uses this to subtract what ``install`` already wrote: a
    project's ``settings.json`` is mostly the merged catalog fragments, so
    translating it wholesale would restate ~every catalog rule in the
    local file.
    """
    _, rules, _ = _expected_text(fragment_paths)
    return {(rule.pattern, rule.decision) for rule in rules}


def write_local_codex_rules(
    codex_dir: Path,
    permissions: dict[str, Any],
    exclude: set[tuple[tuple[str, ...], str]] | None = None,
) -> tuple[str, list[PrefixRule], list[SkippedPermission]]:
    """Write the ``migrate``-owned ``.rules`` file from local permissions.

    ``permissions`` is the project's own merged ``permissions`` object
    (``.claude/settings.json`` + ``settings.local.json``). Rules already
    covered by ``exclude`` — the catalog-derived set — are dropped so the
    two files do not restate each other.

    Returns ``(status, written_rules, skipped)``.

    Raises:
        LinkError: if the file cannot be written or removed.
    """
    rules, skipped = translate_permissions(permissions)
    if exclude:
        rules = [r for r in rules if (r.pattern, r.decision) not in exclude]
    text = render_rules(rules)

    path = local_rules_path(codex_dir)
    existed = path.is_file()
    try:
        if not text:
            if existed:
                path.unlink()
                return "removed", rules, skipped
            return "unchanged", rules, skipped
        if existed and path.read_text(encoding="utf-8") == text:
            return "unchanged", rules, skipped
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise LinkError(f"Failed to write Codex rules {path}: {exc}") from exc

    return ("updated" if existed else "created"), rules, skipped


def strip_codex_rules(codex_dir: Path) -> bool:
    """Remove the ai-dotfiles-owned ``.rules`` file. True if it existed.

    Only ever touches :data:`RULES_FILENAME`; ``default.rules`` and any
    user-authored sibling are left alone. The ``rules/`` directory is
    removed too when this leaves it empty.
    """
    path = rules_path(codex_dir)
    if not path.is_file():
        return False
    try:
        path.unlink()
        parent = path.parent
        if not any(parent.iterdir()):
            parent.rmdir()
    except OSError as exc:
        raise LinkError(f"Failed to remove Codex rules {path}: {exc}") from exc
    return True

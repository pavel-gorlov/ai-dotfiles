"""Assemble ``.mcp.json`` by merging ``mcp.fragment.json`` files.

Each domain may ship an ``mcp.fragment.json`` declaring MCP servers.
On ``ai-dotfiles add`` / ``install`` / ``remove``, the CLI merges those
fragments into ``<project>/.mcp.json`` while preserving any servers the
user wrote by hand.

Merge rules:
  * Server entries are opaque ``dict[str, Any]`` — any per-server key
    (``command``, ``args``, ``env``, ``type``, ``url``, ``headers``,
    ``oauth``, ``headersHelper``, …) round-trips verbatim.
  * Within a single ``assemble`` call, later domain fragments overwrite
    earlier domains' entries for the same server name; ownership tracks
    all contributing domains.
  * On-disk merge: user-authored entries (not in the previous ownership
    map) are preserved; domain-owned entries that disappeared from the
    declarative set are dropped; first-time name collisions keep the
    user version.

Meta keys stripped from fragments before merging: ``_domain``,
``_description``, ``_requires``.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_dotfiles.core.elements import ElementType, parse_element
from ai_dotfiles.core.errors import ConfigError

_META_KEYS: tuple[str, ...] = ("_domain", "_description", "_requires")

# Claude Code env-var syntax: ${VAR} or ${VAR:-default}. NOT ${env:VAR}.
_ENV_TOKEN_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def load_mcp_fragment(path: Path) -> dict[str, Any]:
    """Load an ``mcp.fragment.json`` / ``.mcp.json``-shaped file.

    Returns an empty dict if the file does not exist. Raises
    :class:`ConfigError` on invalid JSON or non-object root.
    """
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in fragment {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read fragment {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Fragment {path} must contain a JSON object at top level")
    return data


def strip_mcp_meta(fragment: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``fragment`` without the meta keys."""
    return {k: v for k, v in fragment.items() if k not in _META_KEYS}


def collect_mcp_fragments(packages: list[str], catalog: Path) -> list[tuple[str, Path]]:
    """Collect ``(domain_name, fragment_path)`` pairs from domain packages.

    Preserves ``packages`` order. Only ``@domain`` specifiers contribute;
    standalones are skipped. Missing fragment files are silently skipped —
    a domain without MCP servers is valid.
    """
    fragments: list[tuple[str, Path]] = []
    for spec in packages:
        try:
            element = parse_element(spec)
        except Exception:  # noqa: BLE001 - ignore non-domain parse failures
            continue
        if element.type is not ElementType.DOMAIN:
            continue
        fragment_path = catalog / element.name / "mcp.fragment.json"
        if fragment_path.exists():
            fragments.append((element.name, fragment_path))
    return fragments


def assemble_mcp_servers(
    fragments: list[tuple[str, Path]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    """Merge fragments in caller-supplied order.

    Returns ``(servers, ownership)`` where:
      * ``servers[name]`` is the last-seen per-server dict for that name.
      * ``ownership[name]`` is the list of all contributing domains in
        encounter order (even when overridden).
    """
    servers: dict[str, dict[str, Any]] = {}
    ownership: dict[str, list[str]] = {}
    for domain_name, path in fragments:
        raw = load_mcp_fragment(path)
        cleaned = strip_mcp_meta(raw)
        mcp_servers = cleaned.get("mcpServers", {})
        if not isinstance(mcp_servers, dict):
            raise ConfigError(f"Fragment {path}: 'mcpServers' must be a JSON object")
        for server_name, server_cfg in mcp_servers.items():
            if not isinstance(server_cfg, dict):
                raise ConfigError(
                    f"Fragment {path}: server '{server_name}' " f"must be a JSON object"
                )
            servers[server_name] = dict(server_cfg)
            contributors = ownership.setdefault(server_name, [])
            if domain_name not in contributors:
                contributors.append(domain_name)
    return servers, ownership


def derive_mcp_permissions(server_names: Iterable[str]) -> list[str]:
    """Return ``["mcp__<name>__*", ...]`` — one wildcard entry per server.

    Deduplicated, preserves first-seen order.
    """
    seen: set[str] = set()
    result: list[str] = []
    for name in server_names:
        if name in seen:
            continue
        seen.add(name)
        result.append(f"mcp__{name}__*")
    return result


def detect_collisions(
    new_servers: dict[str, dict[str, Any]],
    existing: dict[str, Any],
    previous_ownership: dict[str, list[str]],
) -> list[str]:
    """Return server names that are first-time collisions.

    A first-time collision is a name present in both ``existing.mcpServers``
    and ``new_servers`` but NOT in ``previous_ownership`` — meaning the
    user authored it and the CLI has never claimed it. Caller should warn
    and keep the user's version.
    """
    existing_servers = existing.get("mcpServers", {})
    if not isinstance(existing_servers, dict):
        return []
    result: list[str] = []
    for name in new_servers:
        if name in existing_servers and name not in previous_ownership:
            result.append(name)
    return result


def merge_with_existing_mcp(
    new_servers: dict[str, dict[str, Any]],
    existing: dict[str, Any],
    previous_ownership: dict[str, list[str]],
) -> dict[str, Any]:
    """Compose final ``.mcp.json`` payload.

    Rules:
      * User-owned servers (in ``existing.mcpServers`` but not in
        ``previous_ownership``) preserved verbatim.
      * Previously-owned servers missing from ``new_servers`` dropped.
      * ``new_servers`` applied on top, but first-time collisions skipped
        (user version wins).
      * Non-``mcpServers`` top-level keys from ``existing`` preserved.
    """
    result: dict[str, Any] = {}
    for key, value in existing.items():
        if key == "mcpServers":
            continue
        result[key] = value

    existing_servers_raw = existing.get("mcpServers", {})
    existing_servers: dict[str, Any] = (
        dict(existing_servers_raw) if isinstance(existing_servers_raw, dict) else {}
    )

    collisions = set(detect_collisions(new_servers, existing, previous_ownership))

    merged_servers: dict[str, dict[str, Any]] = {}
    for name, cfg in existing_servers.items():
        if name in previous_ownership:
            # Domain-owned; will be re-added from new_servers only if still
            # declared.
            continue
        # User-owned — preserve.
        merged_servers[name] = cfg

    for name, cfg in new_servers.items():
        if name in collisions:
            continue
        merged_servers[name] = cfg

    result["mcpServers"] = merged_servers
    return result


def write_mcp_json(data: dict[str, Any], target: Path) -> None:
    """Write ``data`` as JSON to ``target`` with ``indent=2`` + newline."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def _timestamp() -> str:
    """UTC ISO-8601 timestamp with ``:`` replaced by ``-`` for path safety."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def backup_mcp_json(target: Path, backup_root: Path, project_name: str) -> Path | None:
    """Back up ``target`` to ``<backup_root>/.claude-mcp/<project>/``.

    Returns the backup path, or ``None`` if ``target`` does not exist.
    Never overwrites an existing backup: on same-second collision, appends
    ``.1``, ``.2``, … to the timestamp.
    """
    if not target.exists():
        return None
    dest_dir = backup_root / ".claude-mcp" / project_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    candidate = dest_dir / f".mcp.json.{ts}"
    counter = 0
    while candidate.exists():
        counter += 1
        candidate = dest_dir / f".mcp.json.{ts}.{counter}"
    shutil.copy2(target, candidate)
    return candidate


def _walk_strings(value: Any) -> Iterable[str]:
    """Yield every string embedded in ``value`` (recursively through
    dicts and lists)."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_strings(v)


def warn_unset_env_vars(
    servers: dict[str, dict[str, Any]],
    warn: Callable[[str], None],
    *,
    environ: dict[str, str] | None = None,
) -> None:
    """Scan server configs for ``${VAR}`` tokens with no default and warn
    once per missing variable.

    ``${VAR:-default}`` is considered safe even when ``VAR`` is unset
    (Claude Code substitutes the default at runtime).
    """
    import os

    env = environ if environ is not None else os.environ
    reported: set[str] = set()
    for server_name, cfg in servers.items():
        for text in _walk_strings(cfg):
            for match in _ENV_TOKEN_RE.finditer(text):
                var_name = match.group(1)
                default = match.group(2)
                if default is not None:
                    continue
                if var_name in env:
                    continue
                if var_name in reported:
                    continue
                reported.add(var_name)
                warn(
                    f"MCP server '{server_name}' references ${{{var_name}}} "
                    f"but {var_name} is not set in your shell environment."
                )


def warn_missing_npm_requires(
    fragments: list[tuple[str, Path]],
    project_root: Path,
    warn: Callable[[str], None],
) -> None:
    """For each fragment's ``_requires.npm`` list, warn on packages that
    are missing from ``<project_root>/package.json``.

    Silent if ``package.json`` is absent or unreadable (not every project
    is a Node project).
    """
    pkg_path = project_root / "package.json"
    if not pkg_path.exists():
        return
    try:
        with pkg_path.open("r", encoding="utf-8") as fh:
            pkg = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(pkg, dict):
        return
    known: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        section = pkg.get(key)
        if isinstance(section, dict):
            known.update(section.keys())

    for domain_name, path in fragments:
        raw = load_mcp_fragment(path)
        requires = raw.get("_requires")
        if not isinstance(requires, dict):
            continue
        npm_list = requires.get("npm")
        if not isinstance(npm_list, list):
            continue
        for package in npm_list:
            if not isinstance(package, str):
                continue
            if package in known:
                continue
            warn(
                f"Domain @{domain_name} requires npm package '{package}' "
                f"but it is not in package.json. "
                f"Install with: npm install -D {package}"
            )

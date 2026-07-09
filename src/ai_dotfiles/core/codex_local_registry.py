"""Provenance registry for Codex artefacts generated from LOCAL elements.

Catalog-derived Codex artefacts are reconstructable from the manifest, so
``install --prune`` treats any managed artefact not backed by the manifest as
an orphan and deletes it. Artefacts created by ``ai-dotfiles migrate`` from a
project's own hand-authored ``.claude/`` elements are **not** in the manifest;
without a provenance record ``--prune`` would delete them. This JSON sidecar
(``<root>/.codex/.ai-dotfiles-local.json``) records the local-origin artefacts
so prune protects them and ``reconcile`` can refresh or retire them.

Schema (all keys optional)::

    {
      "skills": {"<name>": "symlink" | "render"},
      "agents": {"<name>": "render"},
      "rule_blocks": {"<agents_md_relpath>": ["<rule_name>", ...]}
    }

A symlinked local skill carries no ``.ai-dotfiles-meta`` sidecar (its target is
the live ``.claude`` source, which must stay clean), so ``--prune`` already
leaves it — but it is still recorded so ``status``/``reconcile`` can see it.
Rendered artefacts (agents, rule-skills, over-cap skills) and always-on /
path-scoped rule blocks are the entries prune must be told to keep.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_dotfiles.core.errors import ConfigError

__all__ = [
    "LOCAL_REGISTRY_FILENAME",
    "delete_local_registry",
    "load_local_registry",
    "registry_path",
    "save_local_registry",
]

LOCAL_REGISTRY_FILENAME = ".ai-dotfiles-local.json"

_EMPTY: dict[str, Any] = {"skills": {}, "agents": {}, "rule_blocks": {}}


def registry_path(project_root: Path) -> Path:
    """Return the local-provenance sidecar path (``<root>/.codex/...``)."""
    return project_root / ".codex" / LOCAL_REGISTRY_FILENAME


def load_local_registry(project_root: Path) -> dict[str, Any]:
    """Return the parsed local registry, or an empty skeleton if absent.

    Raises:
        ConfigError: if the sidecar exists but is not valid JSON.
    """
    path = registry_path(project_root)
    if not path.is_file():
        return {"skills": {}, "agents": {}, "rule_blocks": {}}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - unreadable sidecar
        raise ConfigError(f"Cannot read local registry {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in local registry {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Local registry {path} is not a JSON object")
    return {
        "skills": dict(data.get("skills", {})),
        "agents": dict(data.get("agents", {})),
        "rule_blocks": {k: list(v) for k, v in data.get("rule_blocks", {}).items()},
    }


def save_local_registry(project_root: Path, data: dict[str, Any]) -> None:
    """Write the local registry, or delete it when it holds nothing.

    An empty registry (no skills, agents or rule blocks) is removed rather
    than left as an empty file, keeping the tree tidy and symmetric with the
    other ai-dotfiles ownership sidecars.
    """
    skills = data.get("skills") or {}
    agents = data.get("agents") or {}
    rule_blocks = {k: v for k, v in (data.get("rule_blocks") or {}).items() if v}
    if not skills and not agents and not rule_blocks:
        delete_local_registry(project_root)
        return

    payload = {"skills": skills, "agents": agents, "rule_blocks": rule_blocks}
    path = registry_path(project_root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot write local registry {path}: {exc}") from exc


def delete_local_registry(project_root: Path) -> None:
    """Remove the local registry sidecar if present."""
    path = registry_path(project_root)
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:  # pragma: no cover - unreadable sidecar
        raise ConfigError(f"Cannot delete local registry {path}: {exc}") from exc

"""Read and validate ``catalog/<domain>/domain.json``.

``domain.json`` is the canonical metadata manifest for a domain. It holds
everything that is *about* the domain (identity, dependencies, host
package requirements) but is not part of the runtime config consumed by
Claude Code (``settings.fragment.json``) or by MCP (``mcp.fragment.json``).

Schema::

    {
      "name": "python-backend",
      "description": "FastAPI + async SQLAlchemy backend domain",
      "depends": ["@python"],
      "requires": {
        "npm": ["@playwright/mcp"]
      }
    }

All fields are optional. A domain without ``domain.json`` is valid — it
simply has no metadata, no declared dependencies, and no host-tool
requirements.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ai_dotfiles.core.errors import ConfigError

__all__ = ["DomainMeta", "read_domain_meta", "domain_meta_path"]


@dataclass(frozen=True)
class DomainMeta:
    """Parsed contents of ``domain.json``.

    All fields default to empty / ``None`` so callers can read meta even
    for domains that have no manifest.
    """

    name: str | None = None
    description: str | None = None
    depends: list[str] = field(default_factory=list)
    requires: dict[str, list[str]] = field(default_factory=dict)


def domain_meta_path(catalog: Path, domain_name: str) -> Path:
    """Return the canonical path to a domain's ``domain.json``."""
    return catalog / domain_name / "domain.json"


def read_domain_meta(catalog: Path, domain_name: str) -> DomainMeta:
    """Read ``catalog/<domain_name>/domain.json`` and return a typed view.

    Returns an empty :class:`DomainMeta` if the file does not exist.
    Raises :class:`ConfigError` on JSON or schema violations.
    """
    path = domain_meta_path(catalog, domain_name)
    if not path.is_file():
        return DomainMeta()
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top-level value must be a JSON object")

    name = _coerce_optional_str(data, "name", path)
    description = _coerce_optional_str(data, "description", path)
    depends = _coerce_string_list(data, "depends", path)
    requires = _coerce_requires(data.get("requires"), path)

    return DomainMeta(
        name=name,
        description=description,
        depends=depends,
        requires=requires,
    )


def _coerce_optional_str(data: dict[str, object], key: str, source: Path) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(
            f"{source}: '{key}' must be a string, got {type(value).__name__}"
        )
    return value


def _coerce_string_list(data: dict[str, object], key: str, source: Path) -> list[str]:
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConfigError(
            f"{source}: '{key}' must be a JSON array, got {type(value).__name__}"
        )
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ConfigError(
                f"{source}: every '{key}' entry must be a string, "
                f"got {type(item).__name__}"
            )
        out.append(item)
    return out


def _coerce_requires(value: object, source: Path) -> dict[str, list[str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(
            f"{source}: 'requires' must be a JSON object mapping ecosystem to "
            f"package list, got {type(value).__name__}"
        )
    out: dict[str, list[str]] = {}
    for ecosystem, packages in value.items():
        if not isinstance(ecosystem, str):
            raise ConfigError(
                f"{source}: 'requires' keys must be strings (e.g. 'npm'), "
                f"got {type(ecosystem).__name__}"
            )
        if not isinstance(packages, list):
            raise ConfigError(
                f"{source}: 'requires.{ecosystem}' must be a JSON array, "
                f"got {type(packages).__name__}"
            )
        clean: list[str] = []
        for pkg in packages:
            if not isinstance(pkg, str):
                raise ConfigError(
                    f"{source}: every 'requires.{ecosystem}' entry must be a "
                    f"string, got {type(pkg).__name__}"
                )
            clean.append(pkg)
        out[ecosystem] = clean
    return out

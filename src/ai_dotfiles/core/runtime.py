"""Per-domain runtime provisioning: venvs, shim scripts, host-tool checks.

Domains may ship executable entry points under ``catalog/<domain>/bin/``
and declare host-package requirements in ``domain.json``::

    {
      "requires": {
        "python": ["click>=8", "pyyaml>=6"],
        "cli": ["gh"]
      }
    }

When the domain is installed (project or global scope), this module:

* creates a per-domain virtualenv at ``<storage>/venvs/<domain>`` and
  installs the ``requires.python`` packages into it (using ``uv`` when
  available, falling back to stdlib ``venv`` + ``pip``);
* creates one shim script per ``bin/<name>`` under ``<storage>/bin/``
  that ``exec``s the venv's Python on the catalog entry point;
* checks each ``requires.cli`` tool with :func:`shutil.which` and
  surfaces a warning for those missing on ``PATH``.

The shim carries a header so :func:`tear_down_domain_runtime` only
removes files we own — never user scripts that happen to share a name.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ai_dotfiles.core import paths
from ai_dotfiles.core.domain_meta import read_domain_meta
from ai_dotfiles.core.errors import ExternalError

__all__ = [
    "ProvisionResult",
    "provision_domain_runtime",
    "tear_down_domain_runtime",
    "bin_dir_on_path",
]

_SHIM_HEADER = "# managed-by: ai-dotfiles"
_SHIM_DOMAIN_PREFIX = "# domain: "


@dataclass
class ProvisionResult:
    """Outcome of a single domain provisioning pass."""

    shims_created: list[str] = field(default_factory=list)
    shims_updated: list[str] = field(default_factory=list)
    shims_skipped: list[tuple[str, str]] = field(default_factory=list)
    venv_path: Path | None = None
    python_packages: list[str] = field(default_factory=list)
    missing_cli: list[str] = field(default_factory=list)


def bin_dir_on_path() -> bool:
    """Return True if :func:`paths.bin_dir` is in ``$PATH``."""
    target = paths.bin_dir().resolve()
    raw_path = os.environ.get("PATH", "")
    for entry in raw_path.split(os.pathsep):
        if not entry:
            continue
        try:
            if Path(entry).resolve() == target:
                return True
        except OSError:
            continue
    return False


def _domain_bin_source(catalog: Path, domain_name: str) -> Path:
    return catalog / domain_name / "bin"


def _venv_path(domain_name: str) -> Path:
    return paths.venvs_dir() / domain_name


def _venv_python(venv: Path) -> Path:
    # POSIX layout — the project doesn't target Windows.
    return venv / "bin" / "python"


def _has_uv() -> bool:
    return shutil.which("uv") is not None


def _ensure_venv(venv: Path) -> None:
    if _venv_python(venv).is_file():
        return
    venv.parent.mkdir(parents=True, exist_ok=True)
    cmd: list[str]
    if _has_uv():
        cmd = ["uv", "venv", str(venv)]
    else:
        cmd = ["python3", "-m", "venv", str(venv)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise ExternalError(
            f"Cannot create venv for domain runtime: {cmd[0]} not found on PATH"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise ExternalError(
            f"Failed to create venv at {venv}: {exc.stderr.strip() or exc}"
        ) from exc


def _install_python_packages(venv: Path, packages: list[str]) -> None:
    if not packages:
        return
    py = _venv_python(venv)
    if _has_uv():
        cmd = ["uv", "pip", "install", "--python", str(py), *packages]
    else:
        cmd = [str(py), "-m", "pip", "install", *packages]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise ExternalError(
            f"Failed to install Python packages {packages}: "
            f"{exc.stderr.strip() or exc}"
        ) from exc


def _shim_owner(path: Path) -> str | None:
    """Return the domain name encoded in the shim, or None if not ours."""
    if not path.is_file() or path.is_symlink():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            head = [next(fh, "") for _ in range(4)]
    except OSError:
        return None
    if not any(_SHIM_HEADER in line for line in head):
        return None
    for line in head:
        if line.startswith(_SHIM_DOMAIN_PREFIX):
            return line[len(_SHIM_DOMAIN_PREFIX) :].strip() or None
    return None


def _render_shim(domain_name: str, target: Path, python: Path | None) -> str:
    if python is not None:
        exec_line = f'exec "{python}" "{target}" "$@"\n'
    else:
        exec_line = f'exec "{target}" "$@"\n'
    return (
        "#!/bin/sh\n"
        f"{_SHIM_HEADER}\n"
        f"{_SHIM_DOMAIN_PREFIX}{domain_name}\n"
        "set -e\n"
        f"{exec_line}"
    )


def _write_shim(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _iter_bin_entries(bin_src: Path) -> list[Path]:
    if not bin_src.is_dir():
        return []
    return sorted(p for p in bin_src.iterdir() if p.is_file())


def provision_domain_runtime(
    catalog: Path,
    domain_name: str,
) -> ProvisionResult:
    """Provision venv + shims for a domain. Idempotent.

    Reads ``domain.json``, ensures the venv exists and packages are
    installed when ``requires.python`` is non-empty, generates one shim
    per ``bin/`` entry, and reports missing ``requires.cli`` tools.
    """
    result = ProvisionResult()
    meta = read_domain_meta(catalog, domain_name)
    py_pkgs = list(meta.requires.get("python", []))
    cli_tools = list(meta.requires.get("cli", []))
    bin_src = _domain_bin_source(catalog, domain_name)
    bin_entries = _iter_bin_entries(bin_src)

    if not bin_entries and not py_pkgs and not cli_tools:
        return result

    python_for_shim: Path | None = None
    if py_pkgs:
        venv = _venv_path(domain_name)
        _ensure_venv(venv)
        _install_python_packages(venv, py_pkgs)
        result.venv_path = venv
        result.python_packages = py_pkgs
        python_for_shim = _venv_python(venv)

    for entry in bin_entries:
        shim_path = paths.bin_dir() / entry.name
        body = _render_shim(domain_name, entry.resolve(), python_for_shim)

        existing_owner = _shim_owner(shim_path)
        if shim_path.exists() and existing_owner is None and not shim_path.is_symlink():
            result.shims_skipped.append((entry.name, "user-owned file at target"))
            continue
        if shim_path.is_symlink():
            # Replace stale symlinks (older versions) with shim files.
            shim_path.unlink()

        if shim_path.is_file():
            current = shim_path.read_text(encoding="utf-8")
            if current == body and existing_owner == domain_name:
                continue
            if existing_owner and existing_owner != domain_name:
                result.shims_skipped.append(
                    (entry.name, f"owned by domain '{existing_owner}'")
                )
                continue
            _write_shim(shim_path, body)
            result.shims_updated.append(entry.name)
        else:
            _write_shim(shim_path, body)
            result.shims_created.append(entry.name)

    for tool in cli_tools:
        if shutil.which(tool) is None:
            result.missing_cli.append(tool)

    return result


def tear_down_domain_runtime(catalog: Path, domain_name: str) -> list[str]:
    """Remove shims and venv created by :func:`provision_domain_runtime`.

    Returns a list of shim names that were removed. The venv directory
    is removed in full when it exists. Files at shim paths that don't
    carry our header are left alone.
    """
    removed: list[str] = []

    bin_src = _domain_bin_source(catalog, domain_name)
    bin_dir = paths.bin_dir()
    if bin_dir.is_dir():
        # Walk both the catalog (canonical names) and the bin_dir itself
        # so renamed/removed bin entries still get cleaned up via header.
        seen: set[str] = set()
        for entry in _iter_bin_entries(bin_src):
            shim_path = bin_dir / entry.name
            if _shim_owner(shim_path) == domain_name:
                shim_path.unlink()
                removed.append(entry.name)
                seen.add(entry.name)
        for shim_path in sorted(bin_dir.iterdir()):
            if shim_path.name in seen:
                continue
            if _shim_owner(shim_path) == domain_name:
                shim_path.unlink()
                removed.append(shim_path.name)

    venv = _venv_path(domain_name)
    if venv.is_dir():
        shutil.rmtree(venv)

    return removed

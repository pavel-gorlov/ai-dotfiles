"""Pinned, shell-free Node boundary for native DSH parsing and composition.

Inspection never boots a profile and never calls the mutating CLI dump command.
The reusable ESM also exposes the actual selected-scope audit-before-ready host
boundary; inspection alone is deliberately not a startup/readiness claim.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from importlib import resources
from pathlib import Path
from typing import cast

from ai_dotfiles.core.dsh_render import DshDiagnostic, DshRenderResult
from ai_dotfiles.core.errors import ConfigError, ExternalError

DSH_NATIVE_VERSION = "0.2.0-rc.2"
DSH_NATIVE_SCHEMA_VERSION = 1
DSH_COMPOSE_GENERATOR_VERSION = 3
_NATIVE_PACKAGES = (
    "dsh-app-boot",
    "dsh-skill-filesystem",
    "dsh-mcp-client",
    "dsh-scope",
    "dsh-agent-preset-registry",
)


@dataclass(frozen=True)
class DshNativeRuntime:
    """Verified installed official CLI package, its executable and Node host.

    Resolution does not install anything. package_dir is the directory of
    @deepseek-ai/dsh/package.json, not a shell command or an arbitrary shim.
    """

    package_dir: Path
    node: Path
    cli: Path

    @property
    def install_anchor(self) -> Path:
        return self.package_dir / "package.json"


def _metadata(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ConfigError(f"Cannot read native DSH package {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigError(f"Native DSH package must be an object: {path}")
    return cast(dict[str, object], value)


def resolve_dsh_runtime(
    package_dir: Path, *, node: str | Path = "node"
) -> DshNativeRuntime:
    """Validate official RC2 package/bin metadata without executing a shim.

    The Node helper additionally checks the packages Node actually resolves
    from this installation, including pnpm's own resolution layout.
    """
    package_dir = Path(os.path.abspath(package_dir))
    metadata = _metadata(package_dir / "package.json")
    if (
        metadata.get("name") != "@deepseek-ai/dsh"
        or metadata.get("version") != DSH_NATIVE_VERSION
    ):
        raise ConfigError("Managed DSH requires official @deepseek-ai/dsh 0.2.0-rc.2")
    binary = metadata.get("bin")
    if not isinstance(binary, dict) or binary.get("dsh") != "lib/bin.js":
        raise ConfigError("Unexpected official DSH CLI executable mapping")
    cli = package_dir / "lib/bin.js"
    if not cli.is_file():
        raise ConfigError(f"Missing official DSH CLI executable: {cli}")
    resolved_node = shutil.which(str(node))
    if resolved_node is None:
        raise ExternalError(f"Node executable is unavailable: {node}")
    return DshNativeRuntime(package_dir, Path(resolved_node).absolute(), cli)


def compose_module_text() -> str:
    """Return the packaged reusable native helper; no runtime installation."""
    source = resources.files("ai_dotfiles.scaffold.templates").joinpath(
        "dsh_compose.mjs"
    )
    try:
        return source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"Cannot read shipped DSH composition helper: {exc}") from exc


def invoke_native(
    runtime: DshNativeRuntime,
    request: Mapping[str, object],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: float = 30,
) -> dict[str, object]:
    """Run one strict JSON request through official native APIs, without a shell.

    The caller supplies the complete child environment. Inspection does not
    load dotenv, create a profile, import domain plugins or issue model calls.
    Native diagnostics are returned with source/field/reason, never replaced
    by an empty configuration when parsing, resolution or inspection fails.
    """
    payload = dict(request)
    payload["runtimeAnchor"] = str(runtime.install_anchor)
    try:
        encoded = json.dumps(payload, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ConfigError(f"Invalid native DSH request: {exc}") from exc
    try:
        result = subprocess.run(
            [
                str(runtime.node),
                "--input-type=module",
                "-e",
                compose_module_text() + "\nawait runRequest();\n",
            ],
            input=encoded,
            env=dict(env),
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExternalError(f"Native DSH helper failed: {exc}") from exc
    if result.returncode != 0:
        raise ExternalError(
            f"Native DSH helper exited {result.returncode}: {result.stderr.strip()}"
        )
    try:
        response = json.loads(result.stdout)
    except ValueError as exc:
        raise ConfigError("Native DSH helper returned malformed JSON") from exc
    if (
        not isinstance(response, dict)
        or response.get("schemaVersion") != DSH_NATIVE_SCHEMA_VERSION
        or type(response.get("schemaVersion")) is not int
        or set(response) != {"schemaVersion", "ok", "result", "diagnostics"}
        or type(response.get("ok")) is not bool
        or not isinstance(response.get("result"), dict)
        or not isinstance(response.get("diagnostics"), list)
    ):
        raise ConfigError("Malformed or unsupported native DSH response schema")
    for diagnostic in response["diagnostics"]:
        if (
            not isinstance(diagnostic, dict)
            or set(diagnostic)
            != {"code", "origin", "element", "field", "reason", "blocking"}
            or any(
                not isinstance(diagnostic.get(key), str)
                for key in ("code", "origin", "element", "field", "reason")
            )
            or type(diagnostic.get("blocking")) is not bool
        ):
            raise ConfigError("Malformed native DSH diagnostic")
    if not response["ok"]:
        raise ConfigError(
            "Native DSH inspection refused: "
            + "; ".join(
                f"{item['origin']} {item['element']} {item['field']}: {item['reason']}"
                for item in response["diagnostics"]
            )
        )
    native_result = response["result"]
    if request.get("operation") == "compose":
        if (
            set(native_result)
            != {"entries", "patches", "selection", "diagnostics", "valid", "profile"}
            or native_result.get("valid") is not True
            or not isinstance(native_result.get("entries"), list)
            or not isinstance(native_result.get("patches"), list)
            or not isinstance(native_result.get("diagnostics"), list)
            or not isinstance(native_result.get("profile"), dict)
        ):
            raise ConfigError("Malformed native DSH composition result")
        selection = native_result.get("selection")
        if not isinstance(selection, dict) or (
            selection != {"kind": "global"}
            and (
                set(selection) != {"kind", "id", "entryId"}
                or selection.get("kind") != "preset"
                or any(
                    not isinstance(selection.get(key), str) or not selection[key]
                    for key in ("id", "entryId")
                )
            )
        ):
            raise ConfigError("Malformed native DSH selection result")
    return cast(dict[str, object], native_result)


class DshNativeFrontmatter(dict[Path, dict[str, object]]):
    """Successful native metadata and explicit per-file parse failures."""

    def __init__(
        self,
        metadata: dict[Path, dict[str, object]],
        errors: dict[Path, DshDiagnostic],
    ) -> None:
        super().__init__(metadata)
        self.errors = errors


def native_frontmatter_failure[
    T
](
    result: DshRenderResult[T],
    metadata: Mapping[Path, Mapping[str, object]] | None,
) -> DshRenderResult[T]:
    """Record a failed native parse as MANUAL without fabricating metadata."""
    if not isinstance(metadata, DshNativeFrontmatter):
        return result
    error = metadata.errors.get(result.provenance.source.absolute())
    if error is None:
        return result
    diagnostic = replace(
        error, origin=result.provenance.origin, element=result.provenance.element
    )
    return replace(
        result,
        payload=None,
        status="MANUAL",
        diagnostics=(*result.diagnostics, diagnostic),
    )


def native_frontmatter(
    runtime: DshNativeRuntime,
    sources: Sequence[Path],
    *,
    cwd: Path,
    env: Mapping[str, str],
    strict: bool = True,
) -> DshNativeFrontmatter:
    """Parse original skill/agent/rule frontmatter using DSH's YAML dependency.

    Pass the resulting mapping to collect_dsh_elements(native_frontmatter=...).
    Literal source bytes and whole source bundles stay untouched. A malformed
    file is a precise error rather than a fabricated metadata placeholder.
    """
    result = invoke_native(
        runtime,
        {
            "schemaVersion": DSH_NATIVE_SCHEMA_VERSION,
            "operation": "frontmatter",
            "paths": [str(path.absolute()) for path in sources],
            "strict": strict,
        },
        cwd=cwd,
        env=env,
    )
    metadata = result.get("frontmatter")
    errors = result.get("errors", {})
    requested = {str(path.absolute()) for path in sources}
    if (
        set(result) != ({"frontmatter"} if strict else {"frontmatter", "errors"})
        or not isinstance(metadata, dict)
        or not isinstance(errors, dict)
        or set(metadata) & set(errors)
        or set(metadata) | set(errors) != requested
    ):
        raise ConfigError("Malformed native frontmatter result")
    if any(not isinstance(value, dict) for value in metadata.values()):
        raise ConfigError("Native frontmatter must contain mapping values")
    failures = {}
    for path, error in errors.items():
        if (
            not isinstance(error, dict)
            or set(error)
            != {"code", "origin", "element", "field", "reason", "blocking"}
            or error["code"] != "FRONTMATTER_INVALID"
            or error["origin"] != path
            or error["element"] != path
            or error["field"] != "frontmatter"
            or not isinstance(error["reason"], str)
            or not error["reason"]
            or error["blocking"] is not True
        ):
            raise ConfigError("Malformed native frontmatter failure")
        failures[Path(path)] = DshDiagnostic(**error)
    return DshNativeFrontmatter(
        {
            Path(path): cast(dict[str, object], value)
            for path, value in metadata.items()
        },
        failures,
    )

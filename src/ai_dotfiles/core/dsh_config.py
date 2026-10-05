"""Origin-preserving managed DSH configuration, without native profile writes.

Collect original settings before any Claude merge, keep each source even when
shadowed, and combine global then project logical names before ONE bridge/audit
insertion. Native patch config replacement belongs to the pinned Node helper;
Python never parses YAML or evaluates native expressions.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast
from urllib.parse import urlsplit

from ai_dotfiles.core.dependencies import topological_sort
from ai_dotfiles.core.dsh_audit import (
    DSH_AUDIT_ROW_ID,
    DSH_BRIDGE_ROW_ID,
    DshAuditRequirements,
    bridge_audit_requirements,
    build_bridge_config,
)
from ai_dotfiles.core.dsh_install import (
    DshInstallPlan,
    DshOutput,
    DshResource,
    audit_path,
    plan_dsh_install,
)
from ai_dotfiles.core.dsh_layout import DshLayout
from ai_dotfiles.core.dsh_native import (
    DSH_NATIVE_SCHEMA_VERSION,
    DshNativeRuntime,
    invoke_native,
)
from ai_dotfiles.core.dsh_permissions import (
    DshPermissionPolicy,
    merge_permission_policies,
    translate_permissions,
)
from ai_dotfiles.core.dsh_render import DshDiagnostic, DshProvenance
from ai_dotfiles.core.dsh_targets import DshTargetPlan
from ai_dotfiles.core.elements import Element, ElementType, resolve_source_path
from ai_dotfiles.core.errors import ConfigError

if TYPE_CHECKING:
    from ai_dotfiles.core.dsh_migrate import DshLocalSource


DSH_CONFIG_SCHEMA_VERSION = 1
DSH_CONFIG_GENERATOR_VERSION = 1
DSH_MCP_PACKAGE = "@deepseek-ai/dsh-mcp-client"
Scope = Literal["global", "project"]
SourceKind = Literal["settings", "mcp", "native"]
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_SERVER_NAME = re.compile(r"[A-Za-z0-9_-]{1,32}\Z")
_CLAUDE_ENV = re.compile(r"\$\{[^}]*\}")
# Pinned app-boot's bootstrap names; settings.env gets no home-file exception.
_RESERVED_NAMES = frozenset(
    [
        "PATH",
        "HOME",
        "USERPROFILE",
        "SHELL",
        "NODE_OPTIONS",
        "NODE_PATH",
        "NODE_EXTRA_CA_CERTS",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "LD_AUDIT",
        "BASH_ENV",
        "ENV",
        "SHELLOPTS",
        "BASHOPTS",
        "PERL5OPT",
        "PERL5LIB",
        "PYTHONSTARTUP",
        "PYTHONPATH",
        "RUBYOPT",
        "RUBYLIB",
        "JAVA_TOOL_OPTIONS",
        "_JAVA_OPTIONS",
        "JDK_JAVA_OPTIONS",
        "PYTHONHOME",
        "GIT_SSH",
        "GIT_SSH_COMMAND",
        "GIT_EXTERNAL_DIFF",
        "GIT_PAGER",
        "GIT_EDITOR",
        "GIT_ASKPASS",
        "SSH_ASKPASS",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_SYSTEM",
        "GIT_CONFIG_COUNT",
        "EDITOR",
        "VISUAL",
        "PAGER",
        "BROWSER",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_SEARCH_BASE_URL",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "NODE_TLS_REJECT_UNAUTHORIZED",
    ]
)
_RESERVED_PREFIXES = ("DSH_", "XDG_", "DYLD_", "BASH_FUNC_")


@dataclass(frozen=True)
class DshConfigSource:
    """One original source with explicit scope and installed resource binding.

    binding_root is the copied domain root, or the local source's deliberate
    execution base. Relative plugin/resource paths are bound to it, never to a
    generated patch's directory or an unrelated launch cwd.
    """

    path: Path
    kind: SourceKind
    scope: Scope
    origin: str
    element: str
    binding_root: Path
    local_source: DshLocalSource | None = None


@dataclass(frozen=True)
class DshNativeContribution:
    """One managed logical name supplied by MCP/hooks or another DSH producer.

    Later source wins the same name, but all source records remain in snapshot.
    Rows must already preserve exact native fields. Requirements add to the one
    effective audit; a configured-but-unloaded client must never count as ready.
    Hook producers should supply ONE combined logical contribution, not lose
    global handlers by shadowing an unmerged hooks row with project hooks.
    """

    name: str
    scope: Scope
    rows: tuple[dict[str, object], ...]
    provenance: tuple[DshProvenance, ...]
    requirements: DshAuditRequirements = DshAuditRequirements((), (), (), ())


@dataclass(frozen=True)
class DshConfigPlan:
    """Serializable managed sources, native patches and child env declarations.

    This is a source snapshot, not a frozen user profile or a readiness result.
    ``inspect_dsh_configuration`` selects/merges the actual native composition.
    Outputs attach to DshInstallPlan for its bounded exact ownership preflight.
    """

    layout: DshLayout
    sources: tuple[dict[str, object], ...]
    contributions: tuple[DshNativeContribution, ...]
    domain_patches: tuple[dict[str, object], ...]
    environment: Mapping[str, str]
    permissions: DshPermissionPolicy
    diagnostics: tuple[DshDiagnostic, ...]
    rows: tuple[dict[str, object], ...] = ()
    custom_skill_dirs: tuple[str, ...] = ()
    local_sources: tuple[DshLocalSource, ...] = ()

    @property
    def blocked(self) -> bool:
        return self.permissions.blocked or any(
            item.blocking for item in self.diagnostics
        )

    def require_activatable(self) -> None:
        """Refuse malformed/unsupported restrictions and unresolved inputs."""
        if self.blocked:
            raise ConfigError(
                "Cannot activate managed DSH configuration: "
                + "; ".join(
                    f"{item.origin} {item.element} {item.field}: {item.reason}"
                    for item in (*self.diagnostics, *self.permissions.diagnostics)
                    if item.blocking
                )
            )

    def child_environment(self, process_env: Mapping[str, str]) -> dict[str, str]:
        """Explicit inherited process environment wins, including empty values.

        Never persist the process environment in snapshots or write dotenv.
        Reserved bootstrap names can come only from this explicit process input.
        """
        self.require_activatable()
        return {**self.environment, **process_env}

    def snapshot(self) -> dict[str, object]:
        """Strict schema with all sources, shadowed contributions and diagnostics."""
        data: dict[str, object] = {
            "schemaVersion": DSH_CONFIG_SCHEMA_VERSION,
            "generator": DSH_CONFIG_GENERATOR_VERSION,
            "sources": deepcopy(list(self.sources)),
            "contributions": [_contribution_data(item) for item in self.contributions],
            "domainPatches": deepcopy(list(self.domain_patches)),
            "environment": dict(self.environment),
            "permissions": self.permissions.bridge_data(),
            "diagnostics": [asdict(item) for item in self.diagnostics],
            "rows": deepcopy(list(self.rows)),
            "customSkillDirs": list(self.custom_skill_dirs),
        }
        data["contributionSha256"] = _digest(data)
        return data

    def outputs(self) -> tuple[DshOutput, DshOutput]:
        """Managed snapshot + native root patch, subject to installer ownership.

        A selected-preset launch MUST use the inspected native patches, which
        replace that preset's whole config while preserving its other fields.
        This source patch array alone is not a selected-scope activation claim.
        """
        self.require_activatable()
        provenance = tuple(
            DshProvenance(
                Path(cast(str, item["source"])),
                cast(str, item["origin"]),
                cast(str, item["element"]),
                cast(str, item["source_sha256"]),
                DSH_CONFIG_GENERATOR_VERSION,
            )
            for item in self.sources
        ) + tuple(item for part in self.contributions for item in part.provenance)
        patches = [*deepcopy(self.domain_patches)]
        if self.rows:
            patches.append({"insert": deepcopy(list(self.rows))})
        return (
            DshOutput(
                self.layout.config_path,
                "generated",
                provenance,
                {"config": DSH_CONFIG_GENERATOR_VERSION},
                content=_json(self.snapshot()),
            ),
            DshOutput(
                self.layout.patch_path,
                "generated",
                provenance,
                {"config": DSH_CONFIG_GENERATOR_VERSION},
                content=_json(patches),
            ),
        )


def _json(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"DSH configuration must contain finite JSON data: {exc}"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _contribution_data(item: DshNativeContribution) -> dict[str, object]:
    return {
        "name": item.name,
        "scope": item.scope,
        "rows": deepcopy(list(item.rows)),
        "provenance": [part.as_dict() for part in item.provenance],
        "requirements": item.requirements.as_dict(),
    }


def _validate_data(value: object, field: str) -> None:
    # Reject cycles/non-finite/non-serializable values before recursive walking.
    _json(value)
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ConfigError(f"DSH native fragment {field}: keys must be strings")
            if key == "__jsExpr":
                raise ConfigError(
                    f"DSH native fragment {field}: executable/unsafe marker "
                    f"{key} is forbidden"
                )
            _validate_data(child, f"{field}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_data(child, f"{field}[{index}]")
    elif not isinstance(value, str | bool | int | float | type(None)):
        raise ConfigError(f"DSH native fragment {field}: invalid JSON value")


def _bound_path(value: str, root: Path) -> str:
    if os.path.isabs(value):
        return value
    result = Path(os.path.abspath(root / value))
    if not result.is_relative_to(Path(os.path.abspath(root))):
        raise ConfigError(f"DSH resource escapes its source domain: {value}")
    return str(result)


def validate_native_fragment(
    value: object, *, source: Path, binding_root: Path
) -> list[dict[str, object]]:
    """Validate a data-only native patch array; bind proven native path fields.

    Plugin module paths and Include.path have native filesystem semantics.
    Filesystem customSkillDirs and MCP cwd/relative command paths are also
    proven. Literal persona, descriptions, argv, headers and arbitrary plugin
    values stay exact. Unknown plugin path semantics cannot be guessed.
    Native target/schema/config replacement validation belongs to Node.
    """
    _validate_data(value, str(source))
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ConfigError(
            f"{source}: dsh.fragment.json must be a top-level native patch array"
        )
    patches = cast(list[dict[str, object]], deepcopy(value))

    def bind_config(name: str | None, config: object, at: str) -> None:
        if not isinstance(config, dict):
            return
        if name in ("cordis:include", "@deepseek-ai/cordis-plugin-include"):
            path = config.get("path")
            if isinstance(path, str) and not path.startswith("file:"):
                config["path"] = Path(_bound_path(path, binding_root)).as_uri()
            if "initial" in config:
                rows(config["initial"], at + ".initial")
            include_patches = config.get("patches", [])
            if not isinstance(include_patches, list):
                raise ConfigError(f"{source}: {at}.patches must be an array")
            for index, patch in enumerate(include_patches):
                bind_patch(patch, f"{at}.patches[{index}]")
        elif name == "@deepseek-ai/dsh-skill-filesystem":
            directories = config.get("customSkillDirs")
            if isinstance(directories, list) and all(
                isinstance(item, str) for item in directories
            ):
                config["customSkillDirs"] = [
                    _bound_path(item, binding_root) for item in directories
                ]
        elif name == DSH_MCP_PACKAGE:
            command, cwd = config.get("command"), config.get("cwd")
            if isinstance(command, str) and command.startswith(("./", "../")):
                config["command"] = _bound_path(command, binding_root)
            if isinstance(cwd, str) and cwd:
                config["cwd"] = _bound_path(cwd, binding_root)
        else:
            for key, item in config.items():
                if (
                    key in {"path", "root", "file", "directory", "configPath"}
                    and isinstance(item, str)
                    and item.startswith(("./", "../"))
                ):
                    raise ConfigError(
                        f"{source}: config.{key} relative resource semantics of "
                        f"plugin {name!r} are not proven; use an explicit native "
                        "absolute binding"
                    )

    def rows(items: object, at: str = "insert") -> None:
        if not isinstance(items, list):
            raise ConfigError(f"{source}: native insert/group rows must be an array")
        for index, row in enumerate(items):
            if not isinstance(row, dict) or not isinstance(row.get("name"), str):
                raise ConfigError(
                    f"{source}: native row must have a literal plugin name"
                )
            name = row["name"]
            if "id" not in row:
                identity = hashlib.sha256(
                    f"{source}:{at}[{index}]".encode()
                ).hexdigest()[:16]
                row["id"] = "ai-dotfiles-native-" + identity
            if name.startswith(("./", "../")) or os.path.isabs(name):
                row["name"] = Path(_bound_path(name, binding_root)).as_uri()
            if row.get("group") is True:
                rows(row.get("config"), f"{at}[{index}].config")
            elif name == "@deepseek-ai/dsh-agent-preset":
                config = row.get("config")
                if not isinstance(config, dict):
                    raise ConfigError(
                        f"{source}: native preset config must be an object"
                    )
                rows(config.get("plugins"), f"{at}[{index}].plugins")
            else:
                bind_config(name, row.get("config"), f"{at}[{index}].config")

    def bind_patch(patch: object, at: str) -> None:
        if not isinstance(patch, dict):
            raise ConfigError(f"{source}: {at} must be a native patch mapping")
        if "insert" in patch:
            rows(patch["insert"], at + ".insert")
        elif not isinstance(patch.get("id"), str) or not patch["id"]:
            raise ConfigError(
                f"{source}: non-insert native patch requires a literal id"
            )
        else:
            bind_config(
                cast(str | None, patch.get("name")), patch.get("config"), at + ".config"
            )

    for index, patch in enumerate(patches):
        bind_patch(patch, f"patches[{index}]")
    return patches


def collect_dsh_config_sources(
    elements: Sequence[Element], catalog: Path, layout: DshLayout
) -> tuple[DshConfigSource, ...]:
    """Existing dependency order, no expansion; bind each domain independently."""
    sources: list[DshConfigSource] = []
    scope: Scope = "global" if layout.project_root is None else "project"
    for element in topological_sort(catalog, elements):
        if element.type is not ElementType.DOMAIN:
            continue
        domain = resolve_source_path(element, catalog)
        for filename, kind in (
            ("settings.fragment.json", "settings"),
            ("mcp.fragment.json", "mcp"),
            ("dsh.fragment.json", "native"),
        ):
            path = domain / filename
            if path.exists():
                sources.append(
                    DshConfigSource(
                        path,
                        cast(SourceKind, kind),
                        scope,
                        element.raw,
                        element.raw,
                        layout.resources_dir / "domains" / element.name,
                    )
                )
    return tuple(sources)


def _load(source: DshConfigSource, layout: DshLayout) -> tuple[object, DshProvenance]:
    try:
        raw = source.path.read_bytes()
        value = json.loads(
            raw,
            parse_constant=lambda name: (_ for _ in ()).throw(
                ValueError(f"nonfinite number {name}")
            ),
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise ConfigError(
            f"Cannot read DSH {source.origin} {source.path}: {exc}"
        ) from exc
    if source.local_source is not None:
        from ai_dotfiles.core.dsh_migrate import read_dsh_local_source

        if (
            layout.project_root is None
            or source.scope != "project"
            or source.origin != "local"
            or source.path != source.local_source.path
            or source.kind != source.local_source.kind
            or source.element != source.local_source.provenance.element
            or source.binding_root.absolute() != layout.project_root.absolute()
        ):
            raise ConfigError(
                f"Invalid local DSH config source identity: {source.path}"
            )
        value = read_dsh_local_source(layout.project_root, source.local_source)
    return value, DshProvenance(
        source.path.absolute(),
        source.origin,
        source.element,
        hashlib.sha256(raw).hexdigest(),
        DSH_CONFIG_GENERATOR_VERSION,
    )


def _gap(
    source: DshConfigSource,
    field: str,
    code: str,
    reason: str,
    *,
    blocking: bool = True,
) -> DshDiagnostic:
    return DshDiagnostic(code, source.origin, source.element, field, reason, blocking)


def _strings(value: object) -> bool:
    return isinstance(value, dict) and all(
        isinstance(key, str)
        and isinstance(item, str)
        and "\0" not in key
        and "\0" not in item
        for key, item in value.items()
    )


def _mcp_rows(
    source: DshConfigSource,
    value: dict[str, object],
    provenance: DshProvenance,
    diagnostics: list[DshDiagnostic],
) -> list[DshNativeContribution]:
    result: list[DshNativeContribution] = []
    for key in value.keys() - {"mcpServers"}:
        diagnostics.append(
            _gap(source, key, "MCP_FIELD_UNMAPPED", "unsupported MCP fragment field")
        )
    servers = value.get("mcpServers")
    if not isinstance(servers, dict):
        diagnostics.append(
            _gap(
                source,
                "mcpServers",
                "MCP_INVALID",
                "MCP servers must be a named object",
            )
        )
        return result
    for name, server in servers.items():
        field = f"mcpServers.{name}"
        before = len(diagnostics)
        if not _SERVER_NAME.fullmatch(name) or not isinstance(server, dict):
            diagnostics.append(
                _gap(
                    source,
                    field,
                    "MCP_INVALID",
                    "native serverName must match [A-Za-z0-9_-]{1,32}; "
                    "config must be an object",
                )
            )
            continue
        transport = server.get("type", "stdio" if "command" in server else None)
        if transport not in ("stdio", "http", "streamable-http"):
            diagnostics.append(
                _gap(
                    source,
                    field + ".type",
                    "MCP_TRANSPORT_UNMAPPED",
                    "only stdio and explicit streamable HTTP are supported; "
                    "SSE is not converted",
                )
            )
            continue
        allowed = (
            {"type", "serverName", "command", "args", "env", "cwd"}
            if transport == "stdio"
            else {"type", "serverName", "url", "headers"}
        )
        for key in server.keys() - allowed:
            diagnostics.append(
                _gap(
                    source,
                    field + "." + key,
                    "MCP_FIELD_UNMAPPED",
                    f"native DSH cannot preserve {key} semantics "
                    "(including MCP prompts/oauth/helpers)",
                )
            )
        if "serverName" in server and server["serverName"] != name:
            diagnostics.append(
                _gap(
                    source,
                    field + ".serverName",
                    "MCP_INVALID",
                    "serverName must retain the declared logical MCP name",
                )
            )
        config: dict[str, object] = {
            "serverName": name,
            "transport": "stdio" if transport == "stdio" else "streamable-http",
            "failOnStartupError": True,
        }
        if transport == "stdio":
            command, args, environment, cwd = (
                server.get("command"),
                server.get("args", []),
                server.get("env", {}),
                server.get("cwd", str(source.binding_root)),
            )
            if not isinstance(command, str) or not command or "\0" in command:
                diagnostics.append(
                    _gap(
                        source,
                        field + ".command",
                        "MCP_INVALID",
                        "command must be a nonempty executable string; "
                        "argv is never passed to a shell",
                    )
                )
            if not isinstance(args, list) or any(
                not isinstance(arg, str) or "\0" in arg for arg in args
            ):
                diagnostics.append(
                    _gap(
                        source,
                        field + ".args",
                        "MCP_INVALID",
                        "args must be a string array",
                    )
                )
            if not _strings(environment):
                diagnostics.append(
                    _gap(
                        source,
                        field + ".env",
                        "MCP_INVALID",
                        "env must map names to string values",
                    )
                )
            if not isinstance(cwd, str) or not cwd or "\0" in cwd:
                diagnostics.append(
                    _gap(
                        source,
                        field + ".cwd",
                        "MCP_INVALID",
                        "cwd must be a nonempty path",
                    )
                )
            else:
                cwd = str(Path(os.path.abspath(source.binding_root / cwd)))
            config.update(
                command=(
                    _bound_path(command, source.binding_root)
                    if isinstance(command, str) and command.startswith(("./", "../"))
                    else command
                ),
                args=args,
                env=environment,
                cwd=cwd,
            )
        else:
            url, headers = server.get("url"), server.get("headers", {})
            if (
                not isinstance(url, str)
                or urlsplit(url).scheme not in ("http", "https")
                or not urlsplit(url).netloc
            ):
                diagnostics.append(
                    _gap(
                        source,
                        field + ".url",
                        "MCP_INVALID",
                        "streamable HTTP requires an explicit HTTP(S) URL",
                    )
                )
            if not _strings(headers):
                diagnostics.append(
                    _gap(
                        source,
                        field + ".headers",
                        "MCP_INVALID",
                        "headers must map names to string values",
                    )
                )
            config.update(url=url, headers=headers)

        def tokens(item: object, at: str) -> None:
            if isinstance(item, str) and _CLAUDE_ENV.search(item):
                diagnostics.append(
                    _gap(
                        source,
                        at,
                        "MCP_ENV_UNMAPPED",
                        "Claude ${VAR}/${VAR:-default} expansion and its unset/"
                        "credential-redaction policy have no proven faithful "
                        "translation here; use explicit native values",
                    )
                )
            elif isinstance(item, list):
                for index, child in enumerate(item):
                    tokens(child, f"{at}[{index}]")
            elif isinstance(item, dict):
                for key, child in item.items():
                    tokens(child, f"{at}.{key}")

        tokens(server, field)
        if len(diagnostics) != before:
            continue
        row_id = "ai-dotfiles-mcp-" + name
        result.append(
            DshNativeContribution(
                "mcp:" + name,
                source.scope,
                ({"id": row_id, "name": DSH_MCP_PACKAGE, "config": config},),
                (provenance,),
                DshAuditRequirements((row_id,), (), ("tools",), ()),
            )
        )
    return result


def collect_dsh_configuration(
    sources: Iterable[DshConfigSource],
    layout: DshLayout,
    *,
    contributions: Iterable[DshNativeContribution] = (),
) -> DshConfigPlan:
    """Collect raw source permissions/env/MCP/native patches in stable scope order.

    Malformed values retain source diagnostics and block activation. Removing a
    source means recomputing this declarative union, so other sources survive.
    """
    ordered = sorted(sources, key=lambda source: source.scope == "project")
    records: list[dict[str, object]] = []
    diagnostics: list[DshDiagnostic] = []
    policies: list[DshPermissionPolicy] = []
    env: dict[str, str] = {}
    patches: list[dict[str, object]] = []
    native = list(contributions)
    for source in ordered:
        if source.scope not in ("global", "project") or source.kind not in (
            "settings",
            "mcp",
            "native",
        ):
            raise ConfigError(f"Unknown DSH source scope/kind: {source.path}")
        value, provenance = _load(source, layout)
        if source.local_source is not None:
            for field_name in source.local_source.unproven_fields:
                diagnostics.append(
                    _gap(
                        source,
                        field_name,
                        "LOCAL_ORIGINAL_UNPROVEN",
                        "Claude ownership ledger does not prove the original "
                        "local-user origin of this aggregate field",
                    )
                )
        records.append(
            {
                **provenance.as_dict(),
                "kind": source.kind,
                "scope": source.scope,
                "bindingRoot": str(source.binding_root.absolute()),
                "value": deepcopy(value),
            }
        )
        if source.kind == "native":
            patches.extend(
                validate_native_fragment(
                    value, source=source.path, binding_root=source.binding_root
                )
            )
            continue
        if not isinstance(value, dict):
            raise ConfigError(
                f"{source.path}: DSH {source.kind} source must be an object"
            )
        if source.kind == "mcp":
            native.extend(_mcp_rows(source, value, provenance, diagnostics))
            continue
        if "permissions" in value:
            policies.append(
                translate_permissions(value["permissions"], provenance=provenance)
            )
        for key in value.keys() - {"permissions", "env", "hooks"}:
            diagnostics.append(
                _gap(
                    source,
                    key,
                    "SETTINGS_FIELD_UNMAPPED",
                    "Claude setting has no faithful DSH translation; "
                    "native settings belong in dsh.fragment.json",
                    blocking=False,
                )
            )
        if "env" not in value:
            continue
        environment = value["env"]
        if not _strings(environment):
            diagnostics.append(
                _gap(
                    source,
                    "env",
                    "ENV_INVALID",
                    "settings.env must map valid names to string values",
                )
            )
            continue
        for name, item in cast(dict[str, str], environment).items():
            if not _ENV_NAME.fullmatch(name):
                diagnostics.append(
                    _gap(
                        source,
                        "env." + name,
                        "ENV_INVALID",
                        "invalid environment variable name",
                    )
                )
            elif name.upper() in _RESERVED_NAMES or name.upper().startswith(
                _RESERVED_PREFIXES
            ):
                diagnostics.append(
                    _gap(
                        source,
                        "env." + name,
                        "ENV_RESERVED",
                        "DSH bootstrap variable can only be supplied explicitly "
                        "by the launching process",
                    )
                )
            else:
                env[name] = item
    return DshConfigPlan(
        layout,
        tuple(records),
        tuple(sorted(native, key=lambda item: item.scope == "project")),
        tuple(patches),
        env,
        merge_permission_policies(policies),
        tuple(diagnostics),
        local_sources=tuple(
            source.local_source for source in ordered if source.local_source is not None
        ),
    )


def compose_dsh_configuration(
    config: DshConfigPlan,
    install_plans: Sequence[DshInstallPlan] = (),
    *,
    target_plans: Sequence[DshTargetPlan] = (),
) -> DshConfigPlan:
    """Merge READY source contributions across scopes before one bridge/audit.

    Agent/literal-rule names use global then project precedence; permissions
    retain ALL original restrictions monotonically. Modules bind to config's
    destination layout. Consumer installs must include that layout's generated
    bridge/audit modules; this function cannot adopt foreign files.
    """
    config.require_activatable()
    plans = sorted(install_plans, key=lambda item: item.layout.project_root is not None)
    agents = {
        result.payload.name: result
        for plan in plans
        for result in plan.ready_agents
        if result.payload is not None
    }
    rules = {
        result.payload.name: result
        for plan in plans
        for result in plan.literal_rules
        if result.payload is not None
    }
    permissions = merge_permission_policies(
        [*(plan.permissions for plan in plans), config.permissions]
    )
    bridge = build_bridge_config(
        agents.values(), rules.values(), permissions=permissions
    )
    effective = {item.name: item for item in config.contributions}
    ids: list[str] = []
    tools: list[str] = []
    services: list[str] = []
    providers: list[str] = []
    rows = [
        deepcopy(dict(result.payload.row))
        for result in agents.values()
        if result.payload is not None
    ]
    for item in effective.values():
        rows.extend(deepcopy(item.rows))
        ids.extend(item.requirements.required_ids)
        tools.extend(item.requirements.required_tools)
        services.extend(item.requirements.required_services)
        providers.extend(item.requirements.required_subagent_providers)
    requirements = bridge_audit_requirements(
        bridge,
        required_ids=ids,
        required_tools=tools,
        required_services=services,
        required_subagent_providers=providers,
    )
    rows.extend(
        (
            {
                "id": DSH_BRIDGE_ROW_ID,
                "name": config.layout.bridge_path.absolute().as_uri(),
                "config": bridge,
            },
            {
                "id": DSH_AUDIT_ROW_ID,
                "name": audit_path(config.layout).absolute().as_uri(),
                "config": requirements.as_dict(),
            },
        )
    )
    _validate_rows(rows)
    seen: set[str] = set()
    for row in rows:
        row_id = row.get("id")
        if not isinstance(row_id, str) or not row_id or row_id in seen:
            raise ConfigError(f"Duplicate/invalid managed native row id: {row_id}")
        seen.add(row_id)
    additions = tuple(
        dict.fromkeys(
            str(path) for plan in target_plans for path in plan.custom_skill_dirs
        )
    )
    return replace(
        config, rows=tuple(rows), permissions=permissions, custom_skill_dirs=additions
    )


def attach_dsh_config_outputs(
    install: DshInstallPlan, config: DshConfigPlan
) -> DshInstallPlan:
    """Join generated outputs into the existing installer's ownership transaction."""
    if install.layout != config.layout:
        raise ConfigError("DSH config and install output layouts differ")
    _verify_config_sources(config)
    resources = list(install.resources)
    for source in config.sources:
        provenance = DshProvenance(
            Path(cast(str, source["source"])),
            cast(str, source["origin"]),
            cast(str, source["element"]),
            cast(str, source["source_sha256"]),
            DSH_CONFIG_GENERATOR_VERSION,
        )
        identity = hashlib.sha256(str(provenance.source).encode()).hexdigest()
        resource = DshResource(
            provenance.source, Path("config-sources") / (identity + ".json"), provenance
        )
        if resource not in resources:
            resources.append(resource)
    guarded = plan_dsh_install(
        install.layout,
        skills=install.skills,
        agents=install.agents,
        rules=install.rules,
        resources=resources,
        permissions=install.permissions,
        instructions=install.instructions,
    )
    # Reuse original link/copy modes and externally attached producer outputs.
    keys = {output.path for output in install.outputs}
    return replace(
        install,
        resources=tuple(resources),
        outputs=(
            *install.outputs,
            *(output for output in guarded.outputs if output.path not in keys),
            *config.outputs(),
        ),
    )


def inspect_dsh_configuration(
    config: DshConfigPlan,
    runtime: DshNativeRuntime,
    *,
    profile_dir: Path,
    home: Path,
    cwd: Path,
    process_env: Mapping[str, str],
    cli_patch_files: Sequence[Path] = (),
    selected_preset: str | None = None,
) -> dict[str, object]:
    """Resolve actual native ordering/selection read-only; no readiness claim.

    Bundle -> profile -> home -> managed -> explicit CLI. The returned patches
    are the complete frozen native composition supplied to the managed host.
    Native config replacement is exact; dynamic identity/namespace conflicts
    refuse activation without evaluating their expressions in Python.
    """
    _verify_config_sources(config)
    request: dict[str, object] = {
        "schemaVersion": DSH_NATIVE_SCHEMA_VERSION,
        "operation": "compose",
        "profileDir": str(profile_dir.absolute()),
        "home": str(home.absolute()),
        "cwd": str(cwd.absolute()),
        "domainLayers": [
            {
                "origin": source["origin"],
                "element": source["element"],
                "patches": validate_native_fragment(
                    source["value"],
                    source=Path(cast(str, source["source"])),
                    binding_root=Path(cast(str, source["bindingRoot"])),
                ),
            }
            for source in config.sources
            if source["kind"] == "native"
        ],
        "rows": deepcopy(list(config.rows)),
        "cliPatchFiles": [str(path.absolute()) for path in cli_patch_files],
        "customSkillDirs": list(config.custom_skill_dirs),
        "telemetryDisabledEnv": process_env.get("DSH_TELEMETRY_DISABLED"),
    }
    if selected_preset is not None:
        request["selectedPreset"] = selected_preset
    result = invoke_native(
        runtime, request, cwd=cwd, env=config.child_environment(process_env)
    )
    _verify_config_sources(config)
    return result


def _verify_config_sources(config: DshConfigPlan) -> None:
    if config.local_sources:
        from ai_dotfiles.core.dsh_migrate import read_dsh_local_source

        assert config.layout.project_root is not None
        for local_source in config.local_sources:
            read_dsh_local_source(config.layout.project_root, local_source)
    for source in config.sources:
        path = Path(cast(str, source["source"]))
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ConfigError(f"DSH config source became unavailable: {path}") from exc
        if hashlib.sha256(raw).hexdigest() != source["source_sha256"]:
            raise ConfigError(f"DSH config source changed after planning: {path}")


def _provenance(value: object, *, source: bool = False) -> None:
    keys = {"source", "origin", "element", "source_sha256", "generator"}
    if source:
        keys |= {"kind", "scope", "bindingRoot", "value"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ConfigError("Malformed DSH snapshot provenance")
    if any(
        not isinstance(value[key], str) or not value[key]
        for key in ("source", "origin", "element")
    ) or not os.path.isabs(value["source"]):
        raise ConfigError("Invalid DSH snapshot source identity")
    if (
        not isinstance(value["source_sha256"], str)
        or not re.fullmatch("[0-9a-f]{64}", value["source_sha256"])
        or type(value["generator"]) is not int
        or value["generator"] < 1
    ):
        raise ConfigError("Invalid DSH snapshot provenance hash/generator")
    if source and (
        value["kind"] not in ("settings", "mcp", "native")
        or value["scope"] not in ("global", "project")
        or not isinstance(value["bindingRoot"], str)
        or not os.path.isabs(value["bindingRoot"])
    ):
        raise ConfigError("Invalid DSH snapshot source kind/scope/binding")


def _names(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and item for item in value
    )


def _diagnostic_data(value: object, *, permission: bool = False) -> None:
    keys = {"code", "origin", "element", "field", "reason", "blocking"}
    if permission:
        keys |= {"value", "provenance"}
    if (
        not isinstance(value, dict)
        or set(value) != keys
        or type(value["blocking"]) is not bool
        or any(
            not isinstance(value[key], str)
            for key in ("code", "origin", "element", "field", "reason")
        )
    ):
        raise ConfigError("Malformed DSH snapshot diagnostic")
    if permission:
        _provenance(value["provenance"])


def _permissions_data(value: object) -> None:
    keys = {
        "schemaVersion",
        "generator",
        "deny",
        "ask",
        "requiredTools",
        "blocked",
        "contributions",
        "diagnostics",
    }
    if (
        not isinstance(value, dict)
        or set(value) != keys
        or type(value["schemaVersion"]) is not int
        or value["schemaVersion"] != 1
        or type(value["generator"]) is not int
        or value["generator"] < 1
        or type(value["blocked"]) is not bool
    ):
        raise ConfigError("Malformed/unsupported DSH snapshot permissions")
    if (
        any(not _names(value[key]) for key in ("deny", "ask", "requiredTools"))
        or not isinstance(value["contributions"], list)
        or not isinstance(value["diagnostics"], list)
    ):
        raise ConfigError("Malformed DSH snapshot permission names/contributions")
    for item in value["contributions"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"decision", "entry", "nativeTools", "field", "provenance"}
            or item["decision"] not in ("deny", "ask")
            or not _names(item["nativeTools"])
            or not isinstance(item["entry"], str)
            or not isinstance(item["field"], str)
        ):
            raise ConfigError("Malformed DSH snapshot permission contribution")
        _provenance(item["provenance"])
    for item in value["diagnostics"]:
        _diagnostic_data(item, permission=True)


def read_dsh_config_snapshot(path: Path) -> dict[str, object]:
    """Strict drift reader, never an activation decoder.

    Recollect ORIGINAL current sources and compose/inspect them for launch.
    Source snapshots retain unsupported raw input and cannot be trusted as
    READY payloads merely because this read-only integrity check succeeds.
    """
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ConfigError(f"Cannot read DSH config snapshot {path}: {exc}") from exc
    keys = {
        "schemaVersion",
        "generator",
        "sources",
        "contributions",
        "domainPatches",
        "environment",
        "permissions",
        "diagnostics",
        "rows",
        "customSkillDirs",
        "contributionSha256",
    }
    if (
        not isinstance(value, dict)
        or set(value) != keys
        or type(value.get("schemaVersion")) is not int
        or value["schemaVersion"] != DSH_CONFIG_SCHEMA_VERSION
        or type(value.get("generator")) is not int
        or value["generator"] < 1
    ):
        raise ConfigError(f"Malformed/unsupported DSH config snapshot: {path}")
    for key in (
        "sources",
        "contributions",
        "domainPatches",
        "diagnostics",
        "rows",
        "customSkillDirs",
    ):
        if not isinstance(value[key], list):
            raise ConfigError(f"Invalid DSH snapshot {key}: {path}")
    if not _strings(value["environment"]) or not _names(value["customSkillDirs"]):
        raise ConfigError(f"Invalid DSH snapshot environment/directories: {path}")
    for source in value["sources"]:
        _provenance(source, source=True)
    _permissions_data(value["permissions"])
    for diagnostic in value["diagnostics"]:
        _diagnostic_data(diagnostic)
    for contribution in value["contributions"]:
        if (
            not isinstance(contribution, dict)
            or set(contribution)
            != {"name", "scope", "rows", "provenance", "requirements"}
            or not isinstance(contribution["name"], str)
            or not contribution["name"]
            or contribution["scope"] not in ("global", "project")
            or not isinstance(contribution["rows"], list)
            or not isinstance(contribution["provenance"], list)
        ):
            raise ConfigError("Malformed DSH snapshot native contribution")
        for provenance in contribution["provenance"]:
            _provenance(provenance)
        requirements = contribution["requirements"]
        if (
            not isinstance(requirements, dict)
            or set(requirements)
            != {
                "schemaVersion",
                "generator",
                "requiredIds",
                "requiredTools",
                "requiredServices",
                "requiredSubagentProviders",
            }
            or type(requirements["schemaVersion"]) is not int
            or requirements["schemaVersion"] != 1
            or type(requirements["generator"]) is not int
            or requirements["generator"] < 1
            or any(
                not _names(requirements[key])
                for key in (
                    "requiredIds",
                    "requiredTools",
                    "requiredServices",
                    "requiredSubagentProviders",
                )
            )
        ):
            raise ConfigError("Malformed DSH snapshot audit requirements")
        _validate_rows(contribution["rows"])
    _validate_rows(value["rows"])
    if any(not isinstance(patch, dict) for patch in value["domainPatches"]):
        raise ConfigError("Malformed DSH snapshot native patches")
    _validate_data(value["domainPatches"], "domainPatches")
    if value["contributionSha256"] != _digest(
        {key: child for key, child in value.items() if key != "contributionSha256"}
    ):
        raise ConfigError(f"Modified DSH config snapshot: {path}")
    return cast(dict[str, object], value)


def _validate_rows(rows: object) -> None:
    if not isinstance(rows, list):
        raise ConfigError("Malformed DSH snapshot rows")
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("id"), str)
            or not row["id"]
            or not isinstance(row.get("name"), str)
            or not row["name"]
        ):
            raise ConfigError("Malformed DSH snapshot native row identity")
        config = row.get("config")
        if row["id"] == DSH_BRIDGE_ROW_ID:
            if (
                not isinstance(config, dict)
                or set(config)
                != {"schemaVersion", "generator", "agents", "rules", "permissions"}
                or type(config["schemaVersion"]) is not int
                or config["schemaVersion"] != 1
                or type(config["generator"]) is not int
                or config["generator"] < 1
                or not isinstance(config["agents"], list)
                or not isinstance(config["rules"], list)
            ):
                raise ConfigError("Malformed/unsupported DSH snapshot bridge")
            _permissions_data(config["permissions"])
            for agent in config["agents"]:
                if (
                    not isinstance(agent, dict)
                    or set(agent)
                    != {
                        "name",
                        "toolName",
                        "description",
                        "persona",
                        "sourceModel",
                        "provenance",
                        "rowId",
                        "requiredTools",
                        "toolFilter",
                        "agentOptions",
                    }
                    or any(
                        not isinstance(agent[key], str)
                        for key in (
                            "name",
                            "toolName",
                            "description",
                            "persona",
                            "rowId",
                        )
                    )
                    or not _names(agent["requiredTools"])
                ):
                    raise ConfigError("Malformed DSH snapshot bridge agent")
                _provenance(agent["provenance"])
            for rule in config["rules"]:
                if (
                    not isinstance(rule, dict)
                    or set(rule) != {"name", "body", "description", "provenance"}
                    or any(not isinstance(rule[key], str) for key in ("name", "body"))
                ):
                    raise ConfigError("Malformed DSH snapshot bridge rule")
                _provenance(rule["provenance"])
        elif row["id"] == DSH_AUDIT_ROW_ID:
            if (
                not isinstance(config, dict)
                or set(config)
                != {
                    "schemaVersion",
                    "generator",
                    "requiredIds",
                    "requiredTools",
                    "requiredServices",
                    "requiredSubagentProviders",
                }
                or type(config["schemaVersion"]) is not int
                or config["schemaVersion"] != 1
                or type(config["generator"]) is not int
                or config["generator"] < 1
                or any(
                    not _names(config[key])
                    for key in (
                        "requiredIds",
                        "requiredTools",
                        "requiredServices",
                        "requiredSubagentProviders",
                    )
                )
            ):
                raise ConfigError("Malformed/unsupported DSH snapshot audit")
    _validate_data(rows, "rows")


def dsh_config_drift(config: DshConfigPlan) -> tuple[str, ...]:
    """Source/generator/contribution/patch drift without any filesystem writes.

    Exact file ownership is still checked by installer/reconcile consumers.
    This helper labels declarative drift; it never repairs or adopts a snapshot.
    """
    if not config.layout.config_path.exists():
        return ("MISSING (config)",)
    current = read_dsh_config_snapshot(config.layout.config_path)
    desired = config.snapshot()
    drift: list[str] = []
    if current["generator"] != desired["generator"]:
        drift.append("STALE (generator changed)")
    if current["sources"] != desired["sources"]:
        drift.append("STALE (source changed)")
    if current["contributionSha256"] != desired["contributionSha256"]:
        drift.append("STALE (contribution changed)")
    if not config.blocked:
        patch = config.outputs()[1]
        try:
            if patch.path.read_bytes() != patch.content:
                drift.append("STALE (patch changed)")
        except FileNotFoundError:
            drift.append("MISSING (patch)")
        except OSError as exc:
            raise ConfigError(f"Cannot inspect DSH patch {patch.path}: {exc}") from exc
    return tuple(drift)

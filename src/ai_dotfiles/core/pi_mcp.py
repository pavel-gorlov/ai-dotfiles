"""Compile and reconcile native Pi project MCP entries."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import SplitResult, urlsplit

from ai_dotfiles.core.errors import ConfigError, SourceError
from ai_dotfiles.core.mcp_merge import collect_mcp_fragments

PI_MCP_PATH = Path(".pi/mcp.json")
PI_MCP_GENERATOR_VERSION = 1
_NAME = re.compile(r"[A-Za-z0-9_-]+")
_SHA256 = re.compile(r"[a-f0-9]{64}")
_ENV_REFERENCE = r"\$\{[A-Za-z_][A-Za-z0-9_]*"
_EXPANSION = re.compile(_ENV_REFERENCE + r"(?=\}|:-)")
_DEFAULT = re.compile(_ENV_REFERENCE + r":-")
_DOLLAR = re.compile(_ENV_REFERENCE + r"\}|\$")
_SHARED_FIELDS = {"enabled", "description", "timeout"}
_TRANSPORT_FIELDS = {
    "stdio": {"command", "args", "env", "cwd"},
    "http": {"url", "headers", "oauth"},
}
_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True)
class PiMcpEntryOwnership:
    sha256: str
    fingerprint: str
    generator: int


@dataclass(frozen=True)
class PiMcpOwnership:
    created: bool
    entries: dict[str, PiMcpEntryOwnership]


@dataclass(frozen=True)
class _Server:
    config: dict[str, object]
    ownership: PiMcpEntryOwnership


@dataclass(frozen=True)
class PiMcpPlan:
    servers: dict[str, _Server]
    fingerprint: str


def unique_json(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON properties before a mapping can conceal them."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate property {key!r}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> float:
    raise ValueError(f"invalid JSON number {value}")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("JSON number is out of range")
    return parsed


def _read_config(content: bytes, path: Path) -> dict[str, object]:
    error = ConfigError if path == PI_MCP_PATH else SourceError
    try:
        data = json.loads(
            content.decode("utf-8-sig"),
            object_pairs_hook=unique_json,
            parse_constant=_invalid_constant,
            parse_float=_finite_float,
        )
    except ValueError as exc:
        raise error(f"Invalid Pi MCP config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise error(f"Pi MCP config {path}: expected a JSON object")
    return data


def _read_servers(data: dict[str, object], path: Path) -> dict[str, dict[str, object]]:
    error = ConfigError if path == PI_MCP_PATH else SourceError
    servers = data.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise error(f"Pi MCP config {path}: mcpServers must be a JSON object")
    for name, config in servers.items():
        if not isinstance(config, dict):
            raise error(f"Pi MCP config {path}: server {name!r} must be a JSON object")
    return servers


def _signature(value: object) -> str:
    content = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(content).hexdigest()


def _namespace(name: str) -> str:
    return name.replace("-", "_")


def load_mcp_ownership(value: object) -> PiMcpOwnership:
    """Validate the optional MCP section of the Pi registry."""
    if (
        not isinstance(value, dict)
        or value.keys() != {"created", "entries"}
        or type(value["created"]) is not bool
        or not isinstance(value["entries"], dict)
        or not value["entries"]
    ):
        raise ValueError("invalid MCP ownership")
    entries: dict[str, PiMcpEntryOwnership] = {}
    namespaces: set[str] = set()
    for name, row in value["entries"].items():
        if (
            _NAME.fullmatch(name) is None
            or _namespace(name) in namespaces
            or not isinstance(row, dict)
            or row.keys() != {"sha256", "fingerprint", "generator"}
            or not isinstance(row["sha256"], str)
            or _SHA256.fullmatch(row["sha256"]) is None
            or not isinstance(row["fingerprint"], str)
            or _SHA256.fullmatch(row["fingerprint"]) is None
            or type(row["generator"]) is not int
            or row["generator"] <= 0
        ):
            raise ValueError(f"invalid MCP ownership for {name!r}")
        entries[name] = PiMcpEntryOwnership(
            row["sha256"], row["fingerprint"], row["generator"]
        )
        namespaces.add(_namespace(name))
    return PiMcpOwnership(value["created"], entries)


@dataclass(frozen=True)
class _Source:
    path: Path
    name: str

    def error(self, field: str, message: str) -> SourceError:
        return SourceError(
            f"Pi MCP fragment {self.path}: server {self.name!r}, {field}: {message}"
        )

    def string(self, field: str, value: object, *, resolve: bool = False) -> str:
        if not isinstance(value, str):
            raise self.error(field, "expected a string")
        if not resolve:
            if _EXPANSION.search(value):
                raise self.error(field, "environment references are unsupported")
            return value
        if _DEFAULT.search(value):
            raise self.error(field, "environment defaults are unsupported")
        # Claude references only braced variables. Pi also expands bare variables
        # and executes leading !, so quote those literals for Pi's resolver.
        encoded = _DOLLAR.sub(
            lambda match: "$$" if match[0] == "$" else match[0], value
        )
        return "$" + encoded if encoded.startswith("!") else encoded

    def string_map(self, field: str, value: object) -> dict[str, str]:
        if not isinstance(value, dict):
            raise self.error(field, "expected a map of strings")
        return {
            key: self.string(f"{field}.{key}", item, resolve=True)
            for key, item in value.items()
        }

    def url(self, field: str, value: object) -> SplitResult:
        text = self.string(field, value)
        try:
            parsed = urlsplit(text)
            _ = parsed.port  # Validate the syntax and range of an explicit port.
            if (
                parsed.scheme in {"http", "https"}
                and parsed.hostname
                and not any(character.isspace() for character in parsed.netloc)
            ):
                return parsed
        except ValueError:
            pass
        raise self.error(field, "expected an HTTP or HTTPS URL")

    def oauth(self, value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            raise self.error("oauth", "expected an object")
        strings = {"clientId", "clientName", "clientSecret", "scope"}
        other = {
            "callbackPort",
            "callbackUrl",
            "clientRegistration",
            "authServerMetadataUrl",
        }
        for field in sorted(value.keys() - strings - other):
            raise self.error(f"oauth.{field}", "unsupported field")

        compiled = dict(value)
        for field in sorted(strings & value.keys()):
            compiled[field] = self.string(
                f"oauth.{field}", value[field], resolve=field == "clientSecret"
            )
        client_name = compiled.get("clientName")
        if isinstance(client_name, str) and not client_name.strip():
            raise self.error("oauth.clientName", "expected a non-empty name")
        port = value.get("callbackPort")
        if "callbackPort" in value and (
            type(port) is not int or not 1 <= port <= 65535
        ):
            raise self.error("oauth.callbackPort", "expected a port from 1 to 65535")

        callback = None
        if "callbackUrl" in value:
            callback = self.url("oauth.callbackUrl", value["callbackUrl"])
            if (
                callback.scheme != "http"
                or callback.hostname not in _LOOPBACK
                or callback.query
                or callback.fragment
            ):
                raise self.error(
                    "oauth.callbackUrl", "expected a loopback HTTP redirect URI"
                )
            if port is not None and callback.port is not None and callback.port != port:
                raise self.error(
                    "oauth.callbackPort", "port differs from oauth.callbackUrl"
                )

        if "authServerMetadataUrl" in value:
            metadata = self.url(
                "oauth.authServerMetadataUrl", value["authServerMetadataUrl"]
            )
            if metadata.scheme != "https" and metadata.hostname not in _LOOPBACK:
                raise self.error(
                    "oauth.authServerMetadataUrl", "expected HTTPS or loopback HTTP"
                )

        if "clientRegistration" in value:
            registration = self.string(
                "oauth.clientRegistration", value["clientRegistration"]
            )
            if registration not in {"auto", "dcr", "cimd"}:
                raise self.error(
                    "oauth.clientRegistration", "expected auto, dcr or cimd"
                )
            if registration == "cimd":
                if {"clientId", "clientName"} & value.keys():
                    raise self.error(
                        "oauth.clientRegistration",
                        "cimd cannot specify clientId or clientName",
                    )
                if callback is not None and (
                    callback.hostname == "::1" or callback.path != "/callback"
                ):
                    raise self.error(
                        "oauth.callbackUrl",
                        "cimd requires /callback on localhost or 127.0.0.1",
                    )
        return compiled

    def compile(self, raw: dict[str, object]) -> dict[str, object]:
        transport = raw.get("type")
        if "type" not in raw:
            transport = "http" if "url" in raw else "stdio"
        if transport == "streamable-http":
            transport = "http"
        if transport not in ("stdio", "http"):
            raise self.error("type", "expected stdio or Streamable HTTP")
        unsupported = (
            raw.keys() - _SHARED_FIELDS - _TRANSPORT_FIELDS[transport] - {"type"}
        )
        if unsupported:
            raise self.error(min(unsupported), f"unsupported field for {transport}")
        compiled = {**raw, "type": transport}
        if "enabled" in raw and type(raw["enabled"]) is not bool:
            raise self.error("enabled", "expected a boolean")
        if "description" in raw:
            self.string("description", raw["description"])
        if "timeout" in raw:
            timeout = raw["timeout"]
            if (
                not isinstance(timeout, (int, float))
                or isinstance(timeout, bool)
                or not timeout > 0
            ):
                raise self.error("timeout", "expected a positive number of seconds")
        if transport == "stdio":
            if not self.string("command", raw.get("command")).strip():
                raise self.error("command", "expected a non-empty command")
            if "args" in raw:
                args = raw["args"]
                if not isinstance(args, list):
                    raise self.error("args", "expected an array of strings")
                for index, arg in enumerate(args):
                    self.string(f"args[{index}]", arg)
            if "cwd" in raw:
                self.string("cwd", raw["cwd"])
            if "env" in raw:
                compiled["env"] = self.string_map("env", raw["env"])
        else:
            self.url("url", raw.get("url"))
            if "headers" in raw:
                compiled["headers"] = self.string_map("headers", raw["headers"])
            if "oauth" in raw:
                compiled["oauth"] = self.oauth(raw["oauth"])
        return compiled


def collect_pi_mcp(
    packages: list[str], catalog: Path, read_source: Callable[[Path], bytes]
) -> PiMcpPlan | None:
    """Translate selected raw fragments and record a publication-time fingerprint."""
    fragments = collect_mcp_fragments(packages, catalog, follow_symlinks=False)
    if not fragments:
        return None
    servers: dict[str, _Server] = {}
    namespaces: dict[str, _Source] = {}
    fingerprints: dict[str, str] = {}
    for _, path in fragments:
        content = read_source(path)
        relative = path.relative_to(catalog).as_posix()
        fingerprints[relative] = hashlib.sha256(content).hexdigest()
        for name, raw in _read_servers(_read_config(content, path), path).items():
            source = _Source(path, name)
            if _NAME.fullmatch(name) is None:
                raise source.error(
                    "name", "use ASCII letters, digits, underscores or hyphens"
                )
            namespace = _namespace(name)
            previous = namespaces.get(namespace)
            if previous is not None:
                raise source.error(
                    "name",
                    f"conflicts with {previous.name!r} in {previous.path} "
                    "(Pi namespace)",
                )
            namespaces[namespace] = source
            config = source.compile(raw)
            servers[name] = _Server(
                config,
                PiMcpEntryOwnership(
                    _signature(config),
                    _signature([relative, raw]),
                    PI_MCP_GENERATOR_VERSION,
                ),
            )
    return PiMcpPlan(servers, _signature(fingerprints))


def is_generated_mcp_file(content: bytes, ownership: PiMcpOwnership) -> bool:
    """Only a file created by the installer with solely owned data is generated."""
    if not ownership.created:
        return False
    data = _read_config(content, PI_MCP_PATH)
    servers = _read_servers(data, PI_MCP_PATH)
    return (
        data.keys() == {"mcpServers"}
        and servers.keys() == ownership.entries.keys()
        and all(
            _signature(server) == ownership.entries[name].sha256
            for name, server in servers.items()
        )
    )


def plan_mcp_update(
    current: bytes | None, desired: PiMcpPlan | None, recorded: PiMcpOwnership | None
) -> tuple[bytes | None, PiMcpOwnership | None, list[str]]:
    """Merge only attested entries, keeping all other config data opaque."""
    wanted = desired.servers if desired is not None else {}
    previous = recorded.entries if recorded is not None else {}
    data = _read_config(current, PI_MCP_PATH) if current is not None else {}
    servers = _read_servers(data, PI_MCP_PATH)
    updated = servers.copy()
    drift = []
    changed = False

    signatures = {}
    foreign: dict[str, str] = {}
    for name, config in servers.items():
        if name not in previous:
            foreign.setdefault(_namespace(name), name)
            continue
        signature = _signature(config)
        if signature != previous[name].sha256:
            raise ConfigError(
                f"Pi MCP entry is foreign or was replaced: {PI_MCP_PATH} [{name}]"
            )
        signatures[name] = signature

    for name in sorted(previous.keys() - wanted.keys()):
        drift.append(f"{PI_MCP_PATH} [{name}] RETIRED (no longer selected)")
        if name in updated:
            del updated[name]
            changed = True

    entries = {}
    for name, server in wanted.items():
        conflict = (
            name
            if name in servers and name not in previous
            else foreign.get(_namespace(name))
        )
        if conflict is not None:
            raise ConfigError(
                f"Pi MCP name collision: {PI_MCP_PATH} [{name}] conflicts with "
                f"unmanaged server {conflict!r} (Pi namespace)"
            )
        entries[name] = server.ownership
        label = f"{PI_MCP_PATH} [{name}]"
        if name not in signatures:
            drift.append(f"{label} MISSING")
        elif previous[name].generator != server.ownership.generator:
            drift.append(f"{label} STALE (generator changed)")
        elif previous[name].fingerprint != server.ownership.fingerprint:
            drift.append(f"{label} STALE (source changed)")
        elif signatures[name] != server.ownership.sha256:
            drift.append(f"{label} STALE (generated content changed)")
        if signatures.get(name) != server.ownership.sha256:
            updated[name] = server.config
            changed = True

    created = current is None or (recorded is not None and recorded.created)
    ownership = PiMcpOwnership(created, entries) if entries else None
    if not updated and created and data.keys() <= {"mcpServers"}:
        return None, ownership, drift
    if changed:
        data["mcpServers"] = updated
        current = (json.dumps(data, indent=2) + "\n").encode()
    return current, ownership, drift

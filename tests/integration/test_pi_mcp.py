"""Pi project MCP translation, ownership, and native runtime behavior."""

from __future__ import annotations

import inspect
import json
import os
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Queue
from tempfile import TemporaryFile
from threading import Thread
from time import monotonic
from typing import Any

import pytest
from click.testing import CliRunner

from ai_dotfiles.cli import cli
from ai_dotfiles.core import pi_install
from ai_dotfiles.core.errors import LinkError

pytestmark = pytest.mark.integration
MCP = Path(".pi/mcp.json")
OWNERSHIP = Path(".pi/.ai-dotfiles-ownership.json")
MANIFEST = Path("ai-dotfiles.json")


def invoke(*args: str, expected: int = 0) -> str:
    result = CliRunner().invoke(cli, list(args))
    assert result.exit_code == expected, (result.output, result.exception)
    return result.output


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data) + "\n", encoding="utf-8")


def fragment(catalog: Path, domain: str, servers: dict[str, object]) -> Path:
    directory = catalog / domain
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "domain.json", {"name": domain})
    path = directory / "mcp.fragment.json"
    write_json(path, {"mcpServers": servers})
    return path


@pytest.fixture
def mcp_project(
    tmp_project: Path, tmp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    monkeypatch.chdir(tmp_project)
    invoke("init", "--target", "pi")
    return tmp_project, tmp_storage / "catalog"


def test_mcp_translates_both_transports_and_preserves_existing_config(
    mcp_project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, catalog = mcp_project
    monkeypatch.setenv("MCP_TOKEN", "must-not-be-installed")
    stdio = {
        "command": "pnpm",
        "args": ["exec", "playwright-mcp", "$LITERAL", "!literal"],
        "cwd": "./storybook",
        "env": {
            "MCP_TOKEN": "${MCP_TOKEN}",
            "LITERAL": "!prefix $PRICE $$ $! ${MCP_TOKEN} ${MCP_TOKEN}",
        },
        "timeout": 2.5,
        "description": "Browser fixture",
    }
    http = {
        "type": "streamable-http",
        "url": "http://localhost:6006/mcp",
        "headers": {"Authorization": "Bearer ${MCP_TOKEN}"},
        "oauth": {
            "clientId": "fixture",
            "clientSecret": "!prefix ${MCP_TOKEN}",
            "callbackUrl": "http://127.0.0.1:6710/callback",
            "callbackPort": 6710,
        },
    }
    fragment(catalog, "browser", {"Playwright-local": stdio})
    fragment(catalog, "storybook", {"storybook_HTTP": http})

    path = project / MCP
    path.parent.mkdir()
    existing = {
        "mcpServers": {
            "private": {"command": "custom", "enabled": False, "exposure": "hidden"},
            "global-override": {"enabled": False},
            "playwright_local": {"command": "different-case"},
        },
        "autoEnableCodemode": False,
        "custom": {"preserve": True},
    }
    write_json(path, existing)
    (project / OWNERSHIP).write_text('{"version": 1, "skills": {}}', encoding="utf-8")
    invoke("add", "@browser", "@storybook")

    generated = path.read_bytes()
    updated = json.loads(generated)
    assert updated == {
        **existing,
        "mcpServers": {
            **existing["mcpServers"],
            "Playwright-local": {
                **stdio,
                "type": "stdio",
                "env": {
                    **stdio["env"],
                    "LITERAL": "$!prefix $$PRICE $$$$ $$! ${MCP_TOKEN} ${MCP_TOKEN}",
                },
            },
            "storybook_HTTP": {
                **http,
                "type": "http",
                "oauth": {**http["oauth"], "clientSecret": "$!prefix ${MCP_TOKEN}"},
            },
        },
    }
    registry = json.loads((project / OWNERSHIP).read_bytes())
    assert registry["mcp"]["created"] is False
    assert set(registry["mcp"]["entries"]) == {"Playwright-local", "storybook_HTTP"}
    assert b"must-not-be-installed" not in generated
    status = invoke("status")
    assert f"{MCP} OK\n" in status
    inode = path.stat().st_ino
    invoke("install", "--prune")
    invoke("reconcile", "--check", "--strict")
    assert (path.read_bytes(), path.stat().st_ino) == (generated, inode)

    invoke("remove", "@browser")
    assert set(json.loads(path.read_bytes())["mcpServers"]) == {
        *existing["mcpServers"],
        "storybook_HTTP",
    }
    invoke("remove", "@storybook")
    assert json.loads(path.read_bytes()) == existing
    assert not (project / OWNERSHIP).exists()
    invoke("reconcile", "--check", "--strict")


def test_mcp_dangling_fragment_keeps_previously_installed_servers(
    mcp_project: tuple[Path, Path],
) -> None:
    project, catalog = mcp_project
    source = fragment(catalog, "suite", {"fixture": {"command": "serve"}})
    invoke("add", "@suite")
    files = [project / MCP, project / OWNERSHIP]
    before = [path.read_bytes() for path in files]

    source.unlink()
    source.symlink_to("missing.json")
    output = invoke("reconcile", expected=1)

    assert str(source) in output
    assert [path.read_bytes() for path in files] == before


@pytest.mark.parametrize("retain_file", [False, True])
def test_mcp_reconciles_source_generator_and_missing_drift(
    mcp_project: tuple[Path, Path], retain_file: bool
) -> None:
    project, catalog = mcp_project
    source = fragment(catalog, "suite", {"fixture": {"command": "first"}})
    invoke("add", "@suite")
    path = project / MCP
    registry = project / OWNERSHIP

    ownership = json.loads(registry.read_bytes())
    ownership["mcp"]["entries"]["fixture"]["generator"] += 1
    ownership["hooks"] = {"fingerprint": "0" * 64, "sha256": "0" * 64, "generator": 1}
    write_json(registry, ownership)
    before = path.read_bytes(), registry.read_bytes(), (project / MANIFEST).read_bytes()
    for args in (("status",), ("reconcile", "--check", "--strict")):
        output = invoke(*args, expected=1)
        assert f"{MCP} [fixture] STALE (generator changed)" in output
        assert (
            path.read_bytes(),
            registry.read_bytes(),
            (project / MANIFEST).read_bytes(),
        ) == before
    invoke("reconcile", "--strict")
    assert path.read_bytes() == before[0]
    assert "hooks" not in json.loads(registry.read_bytes())

    write_json(source, {"mcpServers": {"fixture": {"command": "second"}}})
    assert f"{MCP} [fixture] STALE (source changed)" in invoke("status", expected=1)
    invoke("install")
    assert json.loads(path.read_bytes())["mcpServers"]["fixture"]["command"] == "second"

    path.unlink()
    assert f"{MCP} [fixture] MISSING" in invoke("status", expected=1)
    invoke("install")
    assert path.exists()
    invoke("status")

    if retain_file:
        config = json.loads(path.read_bytes())
        config["autoEnableCodemode"] = False
        write_json(path, config)
    source.unlink()
    assert f"{MCP} [fixture] RETIRED" in invoke("reconcile", "--check", expected=1)
    invoke("remove", "@suite")
    assert not registry.exists()
    if retain_file:
        assert json.loads(path.read_bytes()) == {
            "autoEnableCodemode": False,
            "mcpServers": {},
        }
    else:
        assert not path.exists()
    invoke("reconcile", "--check", "--strict")


@pytest.mark.parametrize("conflict", ["foreign-exact", "foreign-alias", "managed-edit"])
def test_mcp_refuses_collisions_and_edited_owned_entries(
    mcp_project: tuple[Path, Path], conflict: str
) -> None:
    project, catalog = mcp_project
    source = {"command": "tool", "type": "stdio"}
    fragment(catalog, "suite", {"api-tools": source})
    path = project / MCP
    registry = project / OWNERSHIP
    if conflict == "managed-edit":
        invoke("add", "@suite")
        before_ownership = registry.read_bytes()
        write_json(path, {"mcpServers": {"api-tools": {**source, "enabled": False}}})
        args = ("remove", "@suite")
        error = "foreign or was replaced"
    else:
        path.parent.mkdir()
        name = "api-tools" if conflict == "foreign-exact" else "api_tools"
        write_json(path, {"mcpServers": {name: source}})
        before_ownership = None
        args = ("add", "@suite")
        error = f"unmanaged server {name!r}"
    before = path.read_bytes(), (project / MANIFEST).read_bytes()
    assert error in invoke(*args, expected=1)
    assert (path.read_bytes(), (project / MANIFEST).read_bytes()) == before
    assert (registry.read_bytes() if registry.exists() else None) == before_ownership


@pytest.mark.parametrize(
    "kind", ["duplicate-key", "same-file-alias", "cross-file", "cross-file-alias"]
)
def test_mcp_detects_collisions_before_fragment_merging(
    mcp_project: tuple[Path, Path], kind: str
) -> None:
    project, catalog = mcp_project
    path = fragment(catalog, "first", {"api-tools": {"command": "tool"}})
    packages = ["@first"]
    if kind == "duplicate-key":
        path.write_text(
            '{"mcpServers":{"api-tools":{"command":"a"},"api-tools":{"command":"b"}}}',
            encoding="utf-8",
        )
        error = "duplicate property 'api-tools'"
    elif kind == "same-file-alias":
        fragment(
            catalog,
            "first",
            {
                "api-tools": {"command": "a"},
                "api_tools": {"command": "b"},
            },
        )
        error = "conflicts with 'api-tools'"
    else:
        alias = "api_tools" if kind == "cross-file-alias" else "api-tools"
        fragment(catalog, "second", {alias: {"command": "tool"}})
        packages.append("@second")
        error = "conflicts with 'api-tools'"
    manifest = (project / MANIFEST).read_bytes()
    output = invoke("add", *packages, expected=1)
    assert error in output and str(path) in output
    assert (project / MANIFEST).read_bytes() == manifest
    assert not (project / ".pi").exists()


@pytest.mark.parametrize(
    ("entry", "field"),
    [
        ({"type": "sse", "url": "https://example.test/mcp"}, "type"),
        ({"command": "tool", "headers": {}}, "headers"),
        ({"args": []}, "command"),
        ({"command": "tool", "args": [True]}, "args[0]"),
        ({"command": "tool", "enabled": "yes"}, "enabled"),
        ({"command": "tool", "timeout": False}, "timeout"),
        ({"command": "${TOOL}"}, "command"),
        ({"command": "tool", "args": ["x/${TOKEN}"]}, "args[0]"),
        ({"command": "tool", "cwd": "${ROOT:-default}"}, "cwd"),
        ({"command": "tool", "env": {"KEY": "${TOKEN:-default}"}}, "env.KEY"),
        ({"type": "http", "url": "https://${SERVER}/mcp"}, "url"),
        ({"type": "http", "url": "https://example.test:noport/mcp"}, "url"),
        ({"url": "http://example.test/mcp", "auth": {"provider": "pi"}}, "auth"),
        ({"url": "http://example.test/mcp", "oauth": True}, "oauth"),
        (
            {"url": "http://example.test/mcp", "oauth": {"clientId": "${ID}"}},
            "oauth.clientId",
        ),
        (
            {
                "url": "http://example.test/mcp",
                "oauth": {"callbackUrl": "https://example.test"},
            },
            "oauth.callbackUrl",
        ),
    ],
)
def test_mcp_source_errors_name_the_file_entry_and_field(
    mcp_project: tuple[Path, Path], entry: dict[str, object], field: str
) -> None:
    project, catalog = mcp_project
    path = fragment(catalog, "bad", {"broken": entry})
    before = (project / MANIFEST).read_bytes()
    output = invoke("add", "@bad", expected=1)
    assert str(path) in output and f"server 'broken', {field}:" in output
    assert (project / MANIFEST).read_bytes() == before
    assert not (project / ".pi").exists()


@pytest.mark.parametrize(
    "content",
    [b"not json", b"null", b'{"mcpServers": []}', b'{"mcpServers": {"other": 42}}'],
)
def test_mcp_rejects_invalid_project_config_without_writing(
    mcp_project: tuple[Path, Path], content: bytes
) -> None:
    project, catalog = mcp_project
    fragment(catalog, "suite", {"fixture": {"command": "tool"}})
    path = project / MCP
    path.parent.mkdir()
    path.write_bytes(content)
    manifest = (project / MANIFEST).read_bytes()
    assert str(MCP) in invoke("add", "@suite", expected=1)
    assert (project / MANIFEST).read_bytes() == manifest
    assert path.read_bytes() == content
    assert not (project / OWNERSHIP).exists()


@pytest.mark.parametrize("changed", ["source-bytes", "source-removed", "destination"])
def test_mcp_rechecks_sources_and_destination_before_commit(
    mcp_project: tuple[Path, Path], changed: str
) -> None:
    project, catalog = mcp_project
    source = fragment(catalog, "suite", {"fixture": {"command": "first"}})
    path = project / MCP
    path.parent.mkdir()
    plan = pi_install.plan_pi_project(
        project, ["@suite"], catalog, ["pi"], original_packages=[]
    )
    assert plan is not None and plan.mcp is not None
    manifest = (project / MANIFEST).read_bytes()
    if changed == "source-bytes":
        source.write_bytes(source.read_bytes() + b"\n")
    elif changed == "source-removed":
        source.unlink()
    else:
        write_json(path, {"mcpServers": {"foreign": {"command": "user"}}})
    before = path.read_bytes() if path.exists() else None
    error = (
        "Pi destination changed after preflight"
        if changed == "destination"
        else "Pi MCP sources changed after preflight"
    )
    with pytest.raises(LinkError, match=error):
        pi_install.apply_pi_project(plan, manifest_change=["@suite"])
    assert (project / MANIFEST).read_bytes() == manifest
    assert (path.read_bytes() if path.exists() else None) == before
    assert not (project / OWNERSHIP).exists()


@pytest.mark.parametrize("verb", ["add", "remove"])
def test_mcp_publication_rollback_and_retry(
    mcp_project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, verb: str
) -> None:
    project, catalog = mcp_project
    fragment(catalog, "suite", {"fixture": {"command": "tool"}})
    path = project / MCP
    registry = project / OWNERSHIP
    path.parent.mkdir()
    path.write_bytes(b'{ "mcpServers" : {"private": {"enabled":false}} }\n')
    if verb == "remove":
        invoke("add", "@suite")
    before = path.read_bytes(), (project / MANIFEST).read_bytes()
    before_ownership = registry.read_bytes() if registry.exists() else None
    replace = os.replace
    failed = False

    def fail_once(source: Path, destination: Path) -> None:
        nonlocal failed
        if destination == project / MANIFEST and not failed:
            failed = True
            raise OSError("injected manifest publication failure")
        replace(source, destination)

    monkeypatch.setattr(pi_install.os, "replace", fail_once)
    assert "injected manifest publication failure" in invoke(verb, "@suite", expected=1)
    assert before == (path.read_bytes(), (project / MANIFEST).read_bytes())
    assert (registry.read_bytes() if registry.exists() else None) == before_ownership
    assert not list(project.glob(".ai-dotfiles-pi-*"))
    invoke(verb, "@suite")
    invoke("install")
    invoke("reconcile", "--check", "--strict")


def _mcp_result(request: dict[str, Any], marker: str) -> dict[str, Any]:
    match request["method"]:
        case "initialize":
            return {
                "protocolVersion": request["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "synthetic-test", "version": "1.0.0"},
            }
        case "tools/list":
            return {
                "tools": [
                    {
                        "name": "fixture-echo",
                        "description": "Return the test marker",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                ]
            }
        case "tools/call":
            return {"content": [{"type": "text", "text": marker}]}
        case _:
            return {}


_STDIO_FIXTURE = """
import json
import os
import sys

for line in sys.stdin:
    request = json.loads(line)
    if "id" in request:
        print(json.dumps({
            "jsonrpc": "2.0", "id": request["id"],
            "result": _mcp_result(request, os.environ["PI_MCP_FIXTURE_VALUE"]),
        }), flush=True)
"""


class _Loopback(BaseHTTPRequestHandler):
    server: _McpFixtureServer

    def log_message(self, *_args: object) -> None:
        pass

    def do_GET(self) -> None:
        self.send_error(405)

    def do_POST(self) -> None:
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/mcp":
            if "id" not in request:
                self.send_response(202)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            result = _mcp_result(request, self.headers["Authorization"])
            self.wfile.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request["id"],
                        "result": result,
                    }
                ).encode()
            )
        elif self.path == "/private-mcp":
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Bearer realm="fixture"')
            self.end_headers()
        elif self.path == "/v1/chat/completions":
            self.stream_model(request)
        else:
            self.send_error(404)

    def stream_model(self, request: dict[str, Any]) -> None:
        server = self.server
        server.requests.append(request)
        if len(server.requests) == 1:
            delta = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": index,
                        "id": f"call_{index}",
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }
                    for index, (name, args) in enumerate(server.calls)
                ],
            }
            reason = "tool_calls"
        else:
            delta = {"role": "assistant", "content": "fixture complete"}
            reason = "stop"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for content, finish in ((delta, None), ({}, reason)):
            chunk = {
                "id": "chatcmpl-mcp-fixture",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": request["model"],
                "choices": [{"index": 0, "delta": content, "finish_reason": finish}],
            }
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


class _McpFixtureServer(ThreadingHTTPServer):
    requests: list[dict[str, Any]]
    calls: list[tuple[str, dict[str, str]]]


def _rpc_prompt(
    pi: Path, project: Path, env: dict[str, str], tools: str
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with (
        TemporaryFile(mode="w+", encoding="utf-8") as errors,
        subprocess.Popen(
            [
                pi,
                "--mode",
                "rpc",
                "--offline",
                "--no-session",
                "--no-skills",
                "--no-context-files",
                "--no-prompt-templates",
                "--model",
                "fixture/fixture",
                "--tools",
                tools,
            ],
            cwd=project,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
            encoding="utf-8",
        ) as process,
    ):
        assert process.stdin is not None and process.stdout is not None
        lines: Queue[str | None] = Queue()

        def collect() -> None:
            for line in process.stdout:
                lines.put(line)
            lines.put(None)

        reader = Thread(target=collect, daemon=True)
        reader.start()
        try:
            process.stdin.write(
                '{"type":"prompt","id":"mcp","message":"MCP fixture"}\n'
            )
            process.stdin.flush()
            deadline = monotonic() + 20
            while True:
                line = lines.get(timeout=max(0, deadline - monotonic()))
                assert line is not None, events
                event = json.loads(line)
                events.append(event)
                if event["type"] == "agent_settled":
                    assert event["aborted"] is False
                    break
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            reader.join(timeout=5)
            errors.seek(0)
            stderr = errors.read()
        assert process.returncode == 0, stderr
    assert any(
        event["type"] == "response"
        and event["id"] == "mcp"
        and event["success"] is True
        for event in events
    ), events
    return events


def _list_mcp(
    pi: Path, project: Path, env: dict[str, str]
) -> tuple[int, dict[str, Any]]:
    result = subprocess.run(
        [pi, "mcp", "list", "--json"],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    return result.returncode, json.loads(result.stdout)


def test_installed_mcp_in_pinned_pi(
    mcp_project: tuple[Path, Path], tmp_path: Path
) -> None:
    configured_pi = os.environ.get("PI_BIN")
    if configured_pi is None:
        pytest.skip("set PI_BIN to the isolated Pi 1.6.1 executable")
    project, catalog = mcp_project
    pi = Path(configured_pi).absolute()
    profile = tmp_path / "pi-profile"
    profile.mkdir()
    home = tmp_path / "pi-home"
    home.mkdir()
    node = shutil.which("node")
    assert node is not None
    env = {
        "PATH": os.pathsep.join((str(Path(node).resolve().parent), "/usr/bin", "/bin")),
        "HOME": str(home),
        "TMPDIR": str(tmp_path),
        "PI_CODING_AGENT_DIR": str(profile),
        "PI_OFFLINE": "1",
        "PI_TELEMETRY": "0",
        "PI_MCP_TOKEN": "local-token",
    }
    version = subprocess.run(
        [pi, "--version"],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert version.stdout.strip() == "1.6.1"
    write_json(
        profile / "settings.json",
        {
            "retry": {"enabled": False, "provider": {"maxRetries": 0}},
        },
    )
    write_json(profile / "trust.json", {str(project.resolve()): True})
    global_mcp = profile / "mcp.json"
    write_json(
        global_mcp,
        {
            "mcpServers": {
                "MCP-stdio": {"command": "global-disabled", "enabled": False}
            },
        },
    )
    global_before = global_mcp.read_bytes()

    stdio = tmp_path / "stdio.py"
    stdio.write_text(
        "from __future__ import annotations\n\n"
        + inspect.getsource(_mcp_result)
        + _STDIO_FIXTURE,
        encoding="utf-8",
    )
    with _McpFixtureServer(("127.0.0.1", 0), _Loopback) as server:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        thread = Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True
        )
        thread.start()
        try:
            write_json(
                profile / "models.json",
                {
                    "providers": {
                        "fixture": {
                            "baseUrl": f"{endpoint}/v1",
                            "apiKey": "fixture",
                            "api": "openai-completions",
                            "models": [{"id": "fixture"}],
                        }
                    }
                },
            )
            fragment(
                catalog,
                "healthy",
                {
                    "MCP-stdio": {
                        "command": sys.executable,
                        "args": [str(stdio)],
                        "env": {
                            "PI_MCP_FIXTURE_VALUE": (
                                "!begin $literal $$ $! ${PI_MCP_TOKEN}"
                            ),
                        },
                    },
                    "MCP_HTTP": {
                        "url": f"{endpoint}/mcp",
                        "headers": {"Authorization": "Bearer ${PI_MCP_TOKEN}"},
                    },
                    "disabled": {"command": "never-run", "enabled": False},
                },
            )
            invoke("add", "@healthy")
            config_path = project / MCP
            installed = config_path.read_bytes()
            exit_code, listing = _list_mcp(pi, project, env)
            assert exit_code == 0 and listing["errors"] == [], listing
            assert [
                (row["name"], row["scope"], row["state"], row["exposure"], row["tools"])
                for row in listing["servers"]
            ] == [
                ("MCP-stdio", "project", "connected", "codemode", ["fixture-echo"]),
                ("MCP_HTTP", "project", "connected", "codemode", ["fixture-echo"]),
                ("disabled", "project", "disabled", "codemode", []),
            ]
            assert listing["servers"][2]["enabled"] is False
            tool_names = ["mcp__MCP_stdio__fixture_echo", "mcp__MCP_HTTP__fixture_echo"]
            markers = ["!begin $literal $$ $! local-token", "Bearer local-token"]
            server.requests = []
            server.calls = [
                (
                    "codemode",
                    {
                        "code": "\n".join(
                            f"text(await tools.{name}({{}}));" for name in tool_names
                        ),
                    },
                )
            ]
            _rpc_prompt(pi, project, env, "codemode")
            assert len(server.requests) == 2
            declared = [
                tool["function"]["name"] for tool in server.requests[0]["tools"]
            ]
            assert declared == ["codemode"]
            replies = [
                message["content"]
                for message in server.requests[1]["messages"]
                if message["role"] == "tool"
            ]
            assert len(replies) == 1 and all(marker in replies[0] for marker in markers)
            assert config_path.read_bytes() == installed

            direct_project = tmp_path / "direct-copy"
            shutil.copytree(project, direct_project)
            direct = json.loads(installed)
            for name in ("MCP-stdio", "MCP_HTTP"):
                direct["mcpServers"][name]["exposure"] = "direct"
            write_json(direct_project / MCP, direct)
            write_json(
                profile / "trust.json",
                {
                    str(project.resolve()): True,
                    str(direct_project.resolve()): True,
                },
            )
            server.requests.clear()
            server.calls = [(name, {}) for name in tool_names]
            _rpc_prompt(pi, direct_project, env, ",".join(tool_names))
            assert len(server.requests) == 2
            assert {
                tool["function"]["name"] for tool in server.requests[0]["tools"]
            } == set(tool_names)
            replies = [
                message["content"]
                for message in server.requests[1]["messages"]
                if message["role"] == "tool"
            ]
            assert replies == markers
            assert config_path.read_bytes() == installed

            fragment(
                catalog,
                "negative",
                {
                    "unavailable": {
                        "command": str(tmp_path / "missing-mcp-executable")
                    },
                    "private": {"url": f"{endpoint}/private-mcp"},
                },
            )
            invoke("add", "@negative")
            exit_code, listing = _list_mcp(pi, project, env)
            by_name = {row["name"]: row for row in listing["servers"]}
            assert exit_code == 1 and listing["errors"] == [], listing
            assert by_name["disabled"]["state"] == "disabled"
            assert by_name["unavailable"]["state"] == "failed"
            assert by_name["unavailable"]["error"]
            assert by_name["unavailable"]["tools"] == []
            assert by_name["private"]["state"] == "needs-auth"
            assert by_name["private"]["tools"] == []
            assert global_mcp.read_bytes() == global_before
            invoke("reconcile", "--check", "--strict")
        finally:
            server.shutdown()
            thread.join(timeout=5)

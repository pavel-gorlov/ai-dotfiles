"""Project lifecycle and the generated Pi hook event bridge."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_dotfiles.cli import cli
from ai_dotfiles.core.errors import LinkError
from ai_dotfiles.core.pi_install import apply_pi_project, plan_pi_project

pytestmark = pytest.mark.integration
EXTENSION = Path(".pi/extensions/ai-dotfiles-hooks.js")
OWNERSHIP = Path(".pi/.ai-dotfiles-ownership.json")
MANIFEST = Path("ai-dotfiles.json")
ROUTE = "gitflow/hooks/route-to-agent.sh"
NUDGE = "gitflow/hooks/pr-review-nudge.sh"
COLLISION = "taskmanager/hooks/tm-collision-check.sh"
MIRROR = "taskmanager/hooks/tm-mirror-push"


def invoke(*args: str, expected: int = 0) -> str:
    result = CliRunner().invoke(cli, list(args))
    assert result.exit_code == expected, (result.output, result.exception)
    return result.output


@pytest.fixture
def hook_project(
    tmp_project: Path, tmp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    monkeypatch.chdir(tmp_project)
    catalog = tmp_storage / "catalog"
    route = "$CLAUDE_PROJECT_DIR/.claude/hooks/route-to-agent.sh"
    nudge = "$CLAUDE_PROJECT_DIR/.claude/hooks/pr-review-nudge.sh"

    def command(text: str, condition: str | None = None) -> dict[str, str]:
        hook = {"type": "command", "command": text}
        if condition is not None:
            hook["if"] = condition
        return hook

    domains = {
        "gitflow": (
            [command(route, "Bash(git *)"), command(route, "Bash(gh *)")],
            "Bash",
            [command(nudge)],
        ),
        "taskmanager": (
            [command("tm-hook collision-check")],
            "Edit|Write",
            [command("tm-hook mirror-push")],
        ),
    }
    for name, (pre, matcher, post) in domains.items():
        domain = catalog / name
        (domain / "hooks").mkdir(parents=True)
        (domain / "domain.json").write_text(json.dumps({"name": name}))
        (domain / "settings.fragment.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [{"matcher": "Bash", "hooks": pre}],
                        "PostToolUse": [{"matcher": matcher, "hooks": post}],
                    }
                }
            )
        )
    for script in (ROUTE, NUDGE, COLLISION, MIRROR):
        (catalog / script).write_text("#!/bin/bash\nexit 0\n")
    invoke("init", "--target", "pi")
    return tmp_project, catalog


def test_hook_lifecycle_preserves_phase_two_registry_and_neighbors(
    hook_project: tuple[Path, Path],
) -> None:
    project, catalog = hook_project
    extension = project / EXTENSION
    extension.parent.mkdir(parents=True)
    neighbor = extension.with_name("private.js")
    neighbor.write_bytes(b"// user extension\n")
    registry = project / OWNERSHIP
    registry.write_text('{"version": 1, "skills": {}}')

    invoke("add", "@taskmanager", "@gitflow")
    initial = extension.read_bytes()
    ownership = json.loads(registry.read_text())
    assert ownership["skills"] == {}
    assert ownership["hooks"]["sha256"] == hashlib.sha256(initial).hexdigest()
    assert initial.count(os.fsencode(catalog.resolve() / ROUTE)) == 2
    assert f"{EXTENSION} OK" in invoke("status")
    invoke("reconcile", "--check", "--strict")
    inode = extension.stat().st_ino
    invoke("install", "--prune")
    assert extension.stat().st_ino == inode
    assert extension.read_bytes() == initial

    (catalog / ROUTE).write_text("#!/bin/bash\n# catalog edit\nexit 0\n")
    assert f"{EXTENSION} STALE (source changed)" in invoke("status", expected=1)
    invoke("reconcile", "--check", "--strict", expected=1)
    invoke("install")
    assert extension.stat().st_ino == inode
    assert (
        ownership["hooks"]["fingerprint"]
        != json.loads(registry.read_text())["hooks"]["fingerprint"]
    )
    assert extension.read_bytes() == initial

    invoke("remove", "@gitflow")
    assert os.fsencode(catalog.resolve() / ROUTE) not in extension.read_bytes()
    extension.unlink()
    assert f"{EXTENSION} MISSING" in invoke("status", expected=1)
    invoke("install")
    assert extension.is_file()
    invoke("remove", "@taskmanager")
    assert not registry.exists()
    assert not extension.exists()
    assert neighbor.read_bytes() == b"// user extension\n"
    assert not (project / ".claude").exists()


@pytest.mark.parametrize("managed", [False, True], ids=["foreign", "modified"])
def test_hook_refuses_replaced_destination(
    hook_project: tuple[Path, Path], managed: bool
) -> None:
    project, _ = hook_project
    extension = project / EXTENSION
    if managed:
        invoke("add", "@gitflow")
    extension.parent.mkdir(parents=True, exist_ok=True)
    extension.write_bytes(b"// user-owned code\n")
    before = (project / MANIFEST).read_bytes()
    output = (
        invoke("remove", "@gitflow", expected=1)
        if managed
        else invoke("add", "@gitflow", expected=1)
    )
    assert f"Pi destination is foreign or was replaced: {EXTENSION}" in output
    assert (project / MANIFEST).read_bytes() == before
    assert extension.read_bytes() == b"// user-owned code\n"


@pytest.mark.parametrize("source", [ROUTE, "gitflow/settings.fragment.json"])
def test_hook_source_errors_stop_before_writes(
    hook_project: tuple[Path, Path], source: str
) -> None:
    project, catalog = hook_project
    target = catalog / source
    original = target.read_text()
    if source == ROUTE:
        target.unlink()
    else:
        target.write_text(original.replace("Bash(git *)", "Bash(*)"))
    manifest = project / MANIFEST
    before = manifest.read_bytes()
    assert str(target) in invoke("add", "@gitflow", expected=1)
    assert manifest.read_bytes() == before
    assert not (project / ".pi").exists()
    target.write_text(original)
    invoke("add", "@gitflow")
    target.unlink()
    assert str(target) in invoke("status", expected=1)


@pytest.mark.parametrize("changed", ["source", "destination"])
def test_hook_rechecks_plan_before_publishing(
    hook_project: tuple[Path, Path], changed: str
) -> None:
    project, catalog = hook_project
    manifest = project / MANIFEST
    before = manifest.read_bytes()
    extension = project / EXTENSION
    extension.parent.mkdir(parents=True)
    plan = plan_pi_project(project, ["@gitflow"], catalog, ["pi"], original_packages=[])
    assert plan is not None and plan.hooks is not None
    foreign = b"// added after preflight\n"
    if changed == "source":
        (catalog / ROUTE).write_text("#!/bin/bash\n# edited after preflight\n")
        error = "Pi hook sources changed after preflight"
    else:
        extension.write_bytes(foreign)
        error = "Pi destination changed after preflight"
    with pytest.raises(LinkError, match=error):
        apply_pi_project(plan, manifest_change=["@gitflow"])
    assert manifest.read_bytes() == before
    assert not (project / OWNERSHIP).exists()
    if changed == "source":
        assert not extension.exists()
    else:
        assert extension.read_bytes() == foreign


HOOK_FIXTURE = r"""
import json
import os
import sys
import time
from pathlib import Path

script = Path(sys.argv[1])
payload = json.load(sys.stdin)
with open(os.environ["PI_HOOK_LOG"], "a") as log:
    log.write(json.dumps({
        "script": str(script), "args": sys.argv[2:], "payload": payload,
        "cwd": os.getcwd(), "project_dir": os.environ["CLAUDE_PROJECT_DIR"],
    }) + "\n")

mode = os.environ.get("PI_HOOK_FIXTURE_MODE")
if script.name == "tm-collision-check.sh":
    if mode == "malformed":
        print("not JSON")
        sys.exit(0)
    if mode == "timeout":
        time.sleep(30)
    if mode == "overflow":
        print("x" * (300 * 1024))
        sys.exit(0)
    if mode == "uncertain":
        print("unable to verify tracker state", file=sys.stderr)
        sys.exit(0)
    if mode in {"deny", "failed-deny"}:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": "confirmed collision",
        }}))
        sys.exit(2 if mode == "failed-deny" else 0)
    sys.exit(0)

command = payload["tool_input"].get("command", "")
if script.name == "tm-mirror-push":
    if mode == "mirror-failure":
        print("mirror sync failed", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)
if mode == "advisory-failure":
    print("advice failed", file=sys.stderr)
    sys.exit(1)
if command.strip().startswith(("git commit", "gh pr create")):
    text = "Gitflow"
    if script.name == "pr-review-nudge.sh":
        text = "PR #17 opened. Continue in Codex or DSH."
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": payload["hook_event_name"], "additionalContext": text,
    }}))
"""


EVENT_FIXTURE = r"""
import assert from "node:assert/strict";
import childProcess from "node:child_process";
import { readFileSync } from "node:fs";
import { syncBuiltinESMExports } from "node:module";
import { basename } from "node:path";
import { pathToFileURL } from "node:url";

const timeouts = new Map();
const spawnSync = childProcess.spawnSync;
childProcess.spawnSync = (executable, args, options) => {
  assert.equal(executable, "bash");
  assert.equal(args.length, 1);
  assert.equal(options.shell, false);
  timeouts.set(basename(args[0]), options.timeout);
  return spawnSync(executable, args, options);
};
syncBuiltinESMExports();
const extension = (await import(pathToFileURL(process.argv[2]))).default;
const callbacks = new Map();
const messages = [];
const notifications = [];
let hasSkill = true;
extension({
  on: (name, callback) => callbacks.set(name, callback),
  getCommands: () => hasSkill ? [{ name: "skill:git-worktree", source: "skill" }] : [],
  sendMessage: (message, options) => messages.push({ message, options }),
});
let transcript;
let trusted = true;
const ctx = {
  cwd: process.cwd(),
  isProjectTrusted: () => trusted,
  sessionManager: {
    getSessionId: () => "pi-fixture",
    getSessionFile: () => transcript,
  },
  ui: { notify: (message, level) => notifications.push({ message, level }) },
};
const pre = (toolName, input) => callbacks.get("tool_call")({ toolName, input }, ctx);
const post = event => callbacks.get("tool_result")(event, ctx);
const structured = { exit_code: 0, output: "https://example.test/test/project/pull/17\n",
  truncated: false, wall_time_seconds: 0.2 };
const bash = { toolName: "bash", input: { command: "gh pr create" },
  isError: false, structuredContent: structured,
  content: [{ type: "text", text: "result" }] };
const write = { toolName: "write", input: {
    path: "tasks/backlog/ais-123_example.md", content: "user data",
    file_path: "untrusted alias" },
  isError: false, content: [{ type: "text", text: "written" }] };

if (process.argv[3] === "mapping") {
  assert.equal(pre("read", { command: "git commit" }), undefined);
  assert.equal(pre("bash", { command: "gitlab status" }), undefined);
  assert.equal(pre("bash", { command: "git status" }), undefined);
  assert.equal(pre("bash", { command: "gh pr view" }), undefined);
  assert.equal(messages.length, 0);
  const command = "  git commit -m 'test; touch SHOULD_NOT_EXIST'";
  assert.equal(pre("bash", { command, timeout: 3 }), undefined);
  transcript = "/isolated/pi-transcript.jsonl";
  hasSkill = false;
  assert.equal(pre("bash", bash.input), undefined);
  assert.equal(messages.length, 2);
  for (const { message, options } of messages) {
    assert.ok(message.content.includes("Codex or DSH"));
    assert.deepEqual(options, { deliverAs: "steer", triggerTurn: true });
  }
  assert.ok(messages[0].message.content.includes("/skill:git-worktree"));
  assert.ok(!messages[1].message.content.includes("/skill:git-worktree"));
  const nudged = post(bash);
  assert.deepEqual(nudged.content.slice(0, 1), bash.content);
  assert.match(nudged.content[1].text, /PR #17 opened/);
  assert.equal(nudged.structuredContent, structured);
  assert.equal(post(write), undefined);
  const edit = { ...write, toolName: "edit", input: { path: write.input.path,
    edits: [{ oldText: "before", newText: "after" }] } };
  assert.equal(post(edit), undefined);
  assert.equal(post({ ...write, isError: true }), undefined);
  assert.equal(post({ ...write, input: { path: "" } }), undefined);
  assert.equal(post({ ...bash, isError: true }), undefined);
  for (const invalid of [{ exit_code: 1 }, { exit_code: null },
    { output: 42 }, { truncated: true }]) {
    assert.equal(post({ ...bash, structuredContent: { ...structured, ...invalid } }),
      undefined);
  }
  assert.equal(post({ ...bash, structuredContent: undefined }), undefined);
  assert.equal(post({ ...bash, details: { truncation: { truncated: true } } }),
    undefined);
  trusted = false;
  assert.equal(pre("bash", bash.input), undefined);
  assert.equal(post(bash), undefined);
  assert.equal(notifications.length, 0);
} else {
  for (const mode of ["malformed", "timeout", "overflow", "uncertain", "failed-deny"]) {
    process.env.PI_HOOK_FIXTURE_MODE = mode;
    assert.equal(pre("bash", { command: "git status" }), undefined);
    assert.equal(notifications.at(-1).level, "warning");
    assert.match(notifications.at(-1).message, /tm-collision-check/);
  }
  assert.equal(notifications.length, 5);
  assert.match(notifications[1].message, /ETIMEDOUT/);
  assert.match(notifications[2].message, /ENOBUFS/);
  process.env.PI_HOOK_FIXTURE_MODE = "deny";
  assert.deepEqual(pre("bash", { command: "git commit" }),
    { block: true, reason: "confirmed collision" });
  process.env.PI_HOOK_FIXTURE_MODE = "mirror-failure";
  assert.equal(post(write), undefined);
  assert.match(notifications.at(-1).message, /mirror sync failed/);
  process.env.PI_HOOK_FIXTURE_MODE = "advisory-failure";
  assert.equal(pre("bash", bash.input), undefined);
  assert.match(notifications.at(-1).message, /route-to-agent-gh/);
  assert.equal(post(bash), undefined);
  assert.match(notifications.at(-1).message, /pr-review-nudge/);
  delete process.env.PI_HOOK_FIXTURE_MODE;
  process.env.PATH = process.env.PI_HOOK_NO_JQ_PATH;
  assert.equal(pre("bash", { command: "git status" }), undefined);
  assert.match(notifications.at(-1).message, /tm-collision-check: jq not found/);
  assert.equal(post(write), undefined);
  assert.match(notifications.at(-1).message, /tm-mirror-push: jq not found/);
  assert.equal(post({ ...bash, input: { command: "gh pr status" } }), undefined);
  assert.match(notifications.at(-1).message, /pr-review-nudge: python3 not found/);
}
assert.deepEqual(Object.fromEntries(timeouts), {
  "route-to-agent.sh": 5_000,
  "tm-collision-check.sh": 5_000,
  "pr-review-nudge.sh": 5_000,
  "tm-mirror-push": 25_000,
});
console.log(readFileSync(process.env.PI_HOOK_LOG, "utf8"));
"""


@pytest.mark.parametrize("case", ["mapping", "failures"])
def test_generated_hook_event_contract(
    hook_project: tuple[Path, Path], case: str
) -> None:
    project, catalog = hook_project
    fixture = project / "fixture.py"
    fixture.write_text(HOOK_FIXTURE)
    runner = project / "events.mjs"
    runner.write_text(EVENT_FIXTURE)
    for script in (ROUTE, NUDGE, COLLISION, MIRROR):
        (catalog / script).write_text(
            '#!/bin/bash\nexec "$PI_HOOK_PYTHON" "$PI_HOOK_FIXTURE" "$0" "$@"\n'
        )
    invoke("add", "@gitflow", "@taskmanager")
    fake = project / ".claude/hooks/route-to-agent.sh"
    fake.parent.mkdir(parents=True)
    fake.write_text("#!/bin/bash\ntouch SHOULD_NOT_EXIST\n")
    fixture_bin = project / "fixture-bin"
    missing_tools = project / "missing-tools"
    bash = shutil.which("bash")
    node = shutil.which("node")
    assert bash is not None and node is not None
    for bin_dir in (fixture_bin, missing_tools):
        bin_dir.mkdir()
        (bin_dir / "bash").symlink_to(bash)
    for name in ("jq", "python3"):
        (fixture_bin / name).symlink_to(sys.executable)
    log = project / "hook-log.jsonl"
    result = subprocess.run(
        [node, str(runner), str(project / EXTENSION), case],
        cwd=project,
        env={
            "PATH": str(fixture_bin),
            "PI_HOOK_LOG": str(log),
            "PI_HOOK_PYTHON": sys.executable,
            "PI_HOOK_FIXTURE": str(fixture),
            "PI_HOOK_NO_JQ_PATH": str(missing_tools),
        },
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not (project / "SHOULD_NOT_EXIST").exists()
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    for row in rows:
        assert row["args"] == []
        assert row["cwd"] == row["project_dir"] == str(project.resolve())
        assert row["payload"]["cwd"] == row["cwd"]
        assert row["payload"]["session_id"] == "pi-fixture"
    if case == "mapping":
        assert [row["script"] for row in rows] == [
            str(catalog.resolve() / relative)
            for relative in (
                COLLISION,
                ROUTE,
                COLLISION,
                ROUTE,
                COLLISION,
                ROUTE,
                COLLISION,
                ROUTE,
                COLLISION,
                NUDGE,
                MIRROR,
                MIRROR,
            )
        ]
        pre = rows[5]["payload"]
        assert pre == {
            "hook_event_name": "PreToolUse",
            "tool_name": "bash",
            "cwd": str(project.resolve()),
            "session_id": "pi-fixture",
            "tool_input": {
                "command": "  git commit -m 'test; touch SHOULD_NOT_EXIST'",
                "timeout": 3,
            },
        }
        nudge, write, edit = (row["payload"] for row in rows[-3:])
        assert nudge == {
            "hook_event_name": "PostToolUse",
            "tool_name": "bash",
            "cwd": str(project.resolve()),
            "session_id": "pi-fixture",
            "transcript_path": "/isolated/pi-transcript.jsonl",
            "tool_input": {"command": "gh pr create"},
            "is_error": False,
            "tool_response": {
                "stdout": "https://example.test/test/project/pull/17\n",
                "exit_code": 0,
            },
        }
        assert [write["tool_name"], edit["tool_name"]] == ["write", "edit"]
        for payload in (write, edit):
            assert payload["hook_event_name"] == "PostToolUse"
            assert payload["is_error"] is False
            assert payload["tool_input"]["file_path"] == payload["tool_input"]["path"]
            assert payload["tool_response"] == [{"type": "text", "text": "written"}]

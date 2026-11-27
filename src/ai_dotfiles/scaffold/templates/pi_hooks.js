import { spawnSync } from "node:child_process";
import { accessSync, constants, statSync } from "node:fs";
import { delimiter, resolve } from "node:path";

const hookTimeoutMs = 5_000;
const mirrorTimeoutMs = 25_000; // tm push uses a 15-second HTTP timeout.
const hookMaxBuffer = 256 * 1024;
const quietPrerequisites = {
  "tm-collision-check": "jq",
  "tm-mirror-push": "jq",
  "pr-review-nudge": "python3",
};

function onPath(command, cwd) {
  return (process.env.PATH ?? "/usr/bin:/bin").split(delimiter).some(directory => {
    const executable = resolve(cwd, directory, command);
    try {
      accessSync(executable, constants.X_OK);
      return statSync(executable).isFile();
    } catch {
      return false;
    }
  });
}

function hookPayload(handler, event, ctx) {
  const toolInput = { ...event.input };
  if (event.toolName === "edit" || event.toolName === "write") {
    toolInput.file_path = event.input.path;
  }
  const payload = {
    hook_event_name: handler.phase,
    tool_name: event.toolName,
    cwd: ctx.cwd,
    session_id: ctx.sessionManager.getSessionId(),
    tool_input: toolInput,
  };
  const transcriptPath = ctx.sessionManager.getSessionFile();
  if (transcriptPath) {
    payload.transcript_path = transcriptPath;
  }
  if (handler.phase === "PostToolUse") {
    const result = event.structuredContent;
    payload.tool_response = event.toolName === "bash"
      ? { stdout: result.output, exit_code: result.exit_code }
      : result ?? event.content;
    payload.is_error = event.isError;
  }
  return payload;
}

function decodeOutput(stdout, handler) {
  const output = JSON.parse(stdout)?.hookSpecificOutput;
  if (!output || output.hookEventName !== handler.phase) {
    throw new Error("Invalid hook response");
  }
  if (handler.id === "tm-collision-check") {
    if (output.permissionDecision !== "deny"
        || typeof output.permissionDecisionReason !== "string"
        || !output.permissionDecisionReason.trim()) {
      throw new Error("Invalid collision-check decision");
    }
  } else if (typeof output.additionalContext !== "string" || !output.additionalContext.trim()) {
    throw new Error("Invalid hook context");
  }
  return output;
}

function runHook(handler, event, ctx) {
  const notify = message => ctx.ui.notify(`ai-dotfiles ${handler.id}: ${message}`, "warning");
  try {
    const result = spawnSync("bash", [handler.script], {
      cwd: ctx.cwd,
      env: { ...process.env, CLAUDE_PROJECT_DIR: ctx.cwd },
      input: JSON.stringify(hookPayload(handler, event, ctx)),
      encoding: "utf8",
      shell: false,
      timeout: handler.id === "tm-mirror-push" ? mirrorTimeoutMs : hookTimeoutMs,
      killSignal: "SIGKILL",
      maxBuffer: hookMaxBuffer,
    });
    const diagnostics = result.stderr?.trim().slice(0, 2000);
    if (result.error || result.status !== 0) {
      const cause = result.error
        ? result.error.message
        : `script exited with ${result.signal ?? result.status ?? "unknown status"}`;
      throw new Error(diagnostics ? `${cause}: ${diagnostics}` : cause);
    }
    if (diagnostics) {
      notify(diagnostics);
    }
    if (result.stdout.trim()) {
      return decodeOutput(result.stdout, handler);
    }
    const prerequisite = quietPrerequisites[handler.id];
    if (!diagnostics && prerequisite && !onPath(prerequisite, ctx.cwd)) {
      notify(`${prerequisite} not found on PATH; hook could not complete`);
    }
  } catch (error) {
    notify(error.message);
  }
}

function steerGitflow(pi) {
  const worktree = pi.getCommands().some(command =>
    command.source === "skill" && command.name === "skill:git-worktree");
  const instruction = worktree ? " For worktree operations, use /skill:git-worktree." : "";
  pi.sendMessage({
    customType: "ai-dotfiles-gitflow",
    content: "Git/PR mutation detected. Hand off Gitflow mutations and PR review to the "
      + "git-workflow-assistant in Codex or DSH for the matching workflow."
      + instruction,
    display: false,
  }, { deliverAs: "steer", triggerTurn: true });
}

export default function (pi) {
  const pre = handlers.filter(handler => handler.phase === "PreToolUse");
  const post = handlers.filter(handler => handler.phase === "PostToolUse");
  pi.on("tool_call", (event, ctx) => {
    if (!ctx.isProjectTrusted()) return;
    const command = event.input.command;
    const family = typeof command === "string"
      ? /^(git|gh)\s/.exec(command.trimStart())?.[1]
      : undefined;
    for (const handler of pre) {
      if (!handler.tools.includes(event.toolName)
          || (handler.commandFamily && handler.commandFamily !== family)) {
        continue;
      }
      const output = runHook(handler, event, ctx);
      if (handler.id === "tm-collision-check" && output?.permissionDecision === "deny") {
        return { block: true, reason: output.permissionDecisionReason };
      }
      if (output?.additionalContext) {
        steerGitflow(pi);
      }
    }
  });
  pi.on("tool_result", (event, ctx) => {
    if (!ctx.isProjectTrusted() || event.isError) return;
    const result = event.structuredContent;
    if (event.toolName === "bash" && (
      result?.exit_code !== 0 || typeof result.output !== "string"
      || result.truncated !== false || event.details?.truncation?.truncated
    )) {
      return;
    }
    if ((event.toolName === "edit" || event.toolName === "write")
        && (typeof event.input.path !== "string" || !event.input.path.trim())) {
      return;
    }
    for (const handler of post) {
      if (!handler.tools.includes(event.toolName)) continue;
      const output = runHook(handler, event, ctx);
      if (handler.id === "pr-review-nudge" && output?.additionalContext) {
        return {
          content: [...event.content, { type: "text", text: output.additionalContext }],
          structuredContent: result,
        };
      }
    }
  });
}

#!/usr/bin/env bash
# PreToolUse hook for the @gitflow domain.
#
# On Bash invocations of mutating git/gh commands, injects a reminder that
# policy (commit format, rebase strategy, force-push safety, PR structure)
# is owned by the `git-workflow-assistant` agent. The hook never blocks —
# it only appends context so the model is nudged to route through the agent
# or follow its policy directly.
#
# Read-only commands (git status, git log, git diff, git fetch, gh pr view,
# ...) do NOT match on purpose — we only nudge on mutations.
set -euo pipefail

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')

pattern='^[[:space:]]*(git[[:space:]]+(commit|rebase|push|merge|cherry-pick|reset[[:space:]]+--hard|revert)|gh[[:space:]]+pr[[:space:]]+(create|merge|edit))\b'

if printf '%s' "$cmd" | grep -Eq "$pattern"; then
  cat <<'JSON'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "Git/PR mutation detected. The @gitflow domain's `git-workflow-assistant` agent owns policy for this project — commit-message format (Conventional Commits 1.0), rebase strategy (including cherry-pick replay), --force-with-lease safety, revert-of-revert handling, PR authoring, worktree workflow, and the quality-gate principle. If you have not already delegated to the agent, either invoke it now or follow its policy body at `.claude/agents/git-workflow-assistant.md` and route through the skill it names for the specific operation."
  }
}
JSON
fi

exit 0

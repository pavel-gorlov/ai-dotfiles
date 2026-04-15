# Hooks

Executable scripts run by Claude Code at specific lifecycle events. They are
referenced from `settings.json` under the `hooks` key.

## Events

- `PreToolUse` — before a tool runs; can block it
- `PostToolUse` — after a tool runs
- `Notification` — on user-visible notifications
- `Stop` — when Claude finishes a turn
- `SubagentStop` — when a subagent finishes

## Matcher

Each hook entry uses a regex-style `matcher` to select tools, e.g.
`Edit|Write`, `Bash(git commit *)`.

## Handler types

- `command` — run a shell command / script
- `intercept` — inline JS/TS handler

## Exit codes

- `0` — allow / continue
- `2` — block with message (stderr is shown to the user)

## Docs

- https://docs.anthropic.com/en/docs/claude-code/hooks

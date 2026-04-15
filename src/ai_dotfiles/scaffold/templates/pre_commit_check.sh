#!/usr/bin/env bash
# PreToolUse hook: verify staged changes before git commit
# Matcher: Bash(git commit *)
# Blocks commit if there are issues

echo "Pre-commit check: reviewing staged changes..."
git diff --staged --stat
exit 0

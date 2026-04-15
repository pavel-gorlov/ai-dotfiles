#!/usr/bin/env bash
# PostToolUse hook: lint files after Edit/Write
# Matcher: Edit|Write
# Runs after Claude edits any file

FILE="$TOOL_INPUT_FILE_PATH"
[[ -z "$FILE" ]] && exit 0

case "$FILE" in
  *.py) ruff check --fix "$FILE" 2>/dev/null ;;
  *.js|*.ts) npx eslint --fix "$FILE" 2>/dev/null ;;
esac
exit 0

#!/usr/bin/env bash
# Example PostToolUse hook for domain "_example"
# Triggered after Edit or Write on files matching the domain
#
# Available environment variables:
#   TOOL_NAME        — name of the tool that was used
#   TOOL_INPUT_*     — tool input parameters (e.g. TOOL_INPUT_FILE_PATH)
#   TOOL_OUTPUT_*    — tool output (e.g. TOOL_OUTPUT_CONTENT)
#   CLAUDE_PROJECT_DIR — project root

FILE="$TOOL_INPUT_FILE_PATH"
[[ -z "$FILE" ]] && exit 0

echo "Example hook: processed $FILE"
exit 0

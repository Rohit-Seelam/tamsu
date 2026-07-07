#!/usr/bin/env bash
# .claude/hooks/load-active.sh
# Wired in settings.json: SessionStart.
#
# Prints the active.json status summary so the orchestrator sees in-flight
# work without having to ask. Output goes to additionalContext (stdout).

set -euo pipefail

ACTIVE_FILE="$CLAUDE_PROJECT_DIR/.claude/active.json"

[[ ! -f "$ACTIVE_FILE" ]] && exit 0

ACTIVE_COUNT=$(jq '.active | length' "$ACTIVE_FILE")
ARCHIVED_COUNT=$(jq '.archived | length' "$ACTIVE_FILE")

printf '## Active workflow state\n\n'
printf 'Active features: %s · Archived: %s\n\n' "$ACTIVE_COUNT" "$ARCHIVED_COUNT"

if [[ "$ACTIVE_COUNT" -gt 0 ]]; then
  printf '### Active\n\n'
  jq -r '.active[] | "- \(.id) (\(.type), phase: \(.phase), started: \(.started))"' "$ACTIVE_FILE"
  printf '\n'
fi

printf 'Use the workflow:status skill for full detail.\n'

exit 0

#!/usr/bin/env bash
# .claude/hooks/enforce-budget.sh
# Wired in settings.json: PostToolUse, matcher Write|Edit|MultiEdit.
#
# Soft-flags artifact files exceeding the budgets in workflow/artifacts.md.
# Does NOT block (exit 0 always). Outputs warning to stderr — Claude sees it as feedback.
#
# Budgets:
#   spec.md      ≤ 150 lines
#   plan.md      ≤ 200 lines
#   findings.md  ≤ 300 lines
#   verification/*-report.md ≤ 100 lines

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')

[[ -z "$FILE_PATH" ]] && exit 0
[[ ! -f "$FILE_PATH" ]] && exit 0

BASE=$(basename "$FILE_PATH")
LINES=$(wc -l < "$FILE_PATH" | tr -d ' ')

CAP=0
case "$BASE" in
  spec.md) CAP=150 ;;
  plan.md) CAP=200 ;;
  findings.md) CAP=300 ;;
  *-report.md)
    [[ "$FILE_PATH" == *"/verification/"* ]] && CAP=100
    ;;
esac

if [[ $CAP -gt 0 && $LINES -gt $CAP ]]; then
  printf 'BUDGET WARNING: %s is %d lines (cap %d).\n' "$FILE_PATH" "$LINES" "$CAP" >&2
  printf 'Consider splitting into linked sub-files per workflow/artifacts.md.\n' >&2
fi

exit 0

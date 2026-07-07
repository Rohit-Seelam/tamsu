#!/usr/bin/env bash
# .claude/hooks/capture-session.sh
# Wired in settings.json:
#   - SubagentStop  → ./capture-session.sh subagent
#   - Stop          → ./capture-session.sh main
#   - PreCompact    → ./capture-session.sh main segment
#
# Copies the raw session .jsonl into sessions/{mainagent|subagents/<name>}/raw/.
# In segment mode (PreCompact), names the file with a session-scoped counter so
# each compaction produces a discrete checkpoint that compile-session.sh can
# compile independently.
#
# Input: hook event JSON on stdin. Reads:
#   .session_id
#   .agent_transcript_path     (SubagentStop only)
#   .transcript_path            (Stop, PreCompact)
#   .agent_name                 (SubagentStop only)
#
# Exit 0 always — observability hook, never blocks.

set -euo pipefail

KIND="${1:-main}"
MODE="${2:-full}"
INPUT=$(cat)

SESSION_ID=$(printf '%s' "$INPUT" | jq -r '.session_id // empty')
TRANSCRIPT=""

case "$KIND" in
  subagent)
    TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.agent_transcript_path // empty')
    AGENT=$(printf '%s' "$INPUT" | jq -r '.agent_name // "unknown"')
    DEST_DIR="$CLAUDE_PROJECT_DIR/.claude/sessions/subagents/$AGENT/raw"
    ;;
  main)
    TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty')
    DEST_DIR="$CLAUDE_PROJECT_DIR/.claude/sessions/mainagent/raw"
    ;;
  *)
    exit 0
    ;;
esac

[[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]] && exit 0
[[ -z "$SESSION_ID" ]] && exit 0

mkdir -p "$DEST_DIR"
TS=$(date -u +"%Y%m%d-%H%M%S")

if [[ "$MODE" == "segment" ]]; then
  COUNTER_DIR="$CLAUDE_PROJECT_DIR/.claude/sessions/.counters"
  COUNTER_FILE="$COUNTER_DIR/${SESSION_ID}.json"
  mkdir -p "$COUNTER_DIR"
  if [[ -f "$COUNTER_FILE" ]]; then
    N=$(jq -r '.n' "$COUNTER_FILE")
    N=$((N + 1))
  else
    N=1
  fi
  printf '{"session_id":"%s","n":%d,"updated":"%s"}\n' "$SESSION_ID" "$N" "$(date -u +%FT%TZ)" > "$COUNTER_FILE"
  cp "$TRANSCRIPT" "$DEST_DIR/${TS}-${SESSION_ID}-segment-${N}.jsonl"
else
  cp "$TRANSCRIPT" "$DEST_DIR/${TS}-${SESSION_ID}.jsonl"
fi

exit 0

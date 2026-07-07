#!/usr/bin/env bash
# .claude/hooks/compile-session.sh
# Wired in settings.json: SessionEnd
#
# Runs the memory:compile skill to turn raw .jsonl into compiled .md.
# Defers to the actual claude-agent-sdk subprocess (TODO — wire after first session).
#
# Exit 0 always — observability hook.

set -euo pipefail

# Placeholder — when claude-agent-sdk is wired:
#   python3 "$CLAUDE_PROJECT_DIR/.claude/skills/memory/compile/scripts/run.py" \
#     --since-last-run \
#     --output-dir "$CLAUDE_PROJECT_DIR/.claude/sessions"

# For now, write a marker so we know the hook fired:
LOG_DIR="$CLAUDE_PROJECT_DIR/.claude/sessions/.hook-log"
mkdir -p "$LOG_DIR"
date -u +"%Y-%m-%dT%H:%M:%SZ SessionEnd compile-session.sh fired" >> "$LOG_DIR/compile.log"

exit 0

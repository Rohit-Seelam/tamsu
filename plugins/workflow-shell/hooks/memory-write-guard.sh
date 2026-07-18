#!/usr/bin/env bash
# .claude/hooks/memory-write-guard.sh
# PreToolUse (Write|Edit|MultiEdit) guard. Enforces the SDK memory pipeline as the SOLE
# memory writer (spec 029, constitution Rule 5). Blocks any non-SDK actor from
# writing the three memory roots; allows the SDK pipeline.
#
# Wired in .claude/settings.json: PreToolUse matcher Write|Edit|MultiEdit.
# Exit 2 = block (stderr shown to the actor as feedback). Exit 0 = allow.
#
# Input: tool-call JSON on stdin. Reads:
#   .tool_name              e.g. "Write", "Edit"
#   .tool_input.file_path   target path
#
# The block/allow decision derives ONLY from the tool_input path and an actor env
# signal — never from orchestrator context state or a prompt directive (AC-10).
# Actor signal resolved empirically in
# specs/029-memory-sdk-sole-writer/verification/probe-actor-signal.md.

set -euo pipefail

INPUT=$(cat)

# Security guard ⇒ fail CLOSED: without jq we cannot parse the tool call, so we cannot prove the
# write is safe. Blocking with a clear remedy beats silently waving every memory write through
# (exit 127 would fail OPEN — the one failure mode a sole-writer guard must not have).
if ! command -v jq >/dev/null 2>&1; then
  printf 'BLOCKED by memory-write-guard.sh — jq is not installed, so tool calls cannot be inspected.\n' >&2
  printf 'This guard fails closed. Install jq (macOS: brew install jq) and retry.\n' >&2
  exit 2
fi

TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty')

case "$TOOL" in
  Write|Edit|MultiEdit) ;;
  *) exit 0 ;;
esac

FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')
[[ -z "$FILE_PATH" ]] && exit 0

# The three memory roots. Each branch also catches the doubly-nested wrong-cwd
# shape (e.g. .claude/.claude/agent-memory/), because the inner ".claude/<root>/"
# segment is itself a substring of the nested path:
#   canonical auto-load   ~/.claude/projects/<slug>/memory/
#   repo mirror           <repo>/.claude/memory/
#   per-agent silos       <repo>/.claude/agent-memory/  (live SDK-written store
#                         for the 7 silo agents; guarded so only the SDK writes it)
MEMORY_PATH_RE='(\.claude/projects/[^/]+/memory/)|(\.claude/memory/)|(\.claude/agent-memory/)'

if ! printf '%s' "$FILE_PATH" | grep -qE "$MEMORY_PATH_RE"; then
  exit 0   # not a memory path — never over-block ordinary writes (AC-11)
fi

# Memory path. Allow ONLY the SDK pipeline, identified by its distinct process
# identity (CLAUDE_CODE_ENTRYPOINT=sdk-py, set unconditionally by
# claude-agent-sdk) OR the explicit launcher marker (SDK_MEMORY_PIPELINE=1).
if [[ "${CLAUDE_CODE_ENTRYPOINT:-}" == "sdk-py" || "${SDK_MEMORY_PIPELINE:-}" == "1" ]]; then
  exit 0
fi

block() {
  printf 'BLOCKED by .claude/hooks/memory-write-guard.sh — %s on %s\n' "$TOOL" "$FILE_PATH" >&2
  printf 'Reason: the SDK memory pipeline is the SOLE memory writer (spec 029, constitution Rule 5).\n' >&2
  printf 'Orchestrator and subagents MUST NOT write .claude/memory/, .claude/agent-memory/, or ~/.claude/projects/<slug>/memory/.\n' >&2
  printf 'Memory updates land via the SDK pipeline at deliver; do not write these paths directly.\n' >&2
  exit 2
}

block

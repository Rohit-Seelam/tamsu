#!/usr/bin/env bash
# .claude/hooks/lint-on-write.sh
# Wired in settings.json: PostToolUse, matcher Write|Edit|MultiEdit.
#
# Runs the appropriate linter for the file just written. Surfaces output
# to stderr so Claude sees it. Does not block (exit 0 always).

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')

[[ -z "$FILE_PATH" ]] && exit 0
[[ ! -f "$FILE_PATH" ]] && exit 0

case "$FILE_PATH" in
  *.go)
    if command -v gofmt >/dev/null; then
      OUT=$(gofmt -l "$FILE_PATH" 2>&1 || true)
      [[ -n "$OUT" ]] && printf 'gofmt: %s needs formatting\n' "$FILE_PATH" >&2
    fi
    if command -v go >/dev/null; then
      DIR=$(dirname "$FILE_PATH")
      go vet "./$DIR/..." 2>&1 | head -20 >&2 || true
    fi
    ;;
  *.ts|*.tsx)
    if [[ -f "$CLAUDE_PROJECT_DIR/package.json" ]] && command -v npm >/dev/null; then
      cd "$CLAUDE_PROJECT_DIR"
      npm run lint -- "$FILE_PATH" 2>&1 | tail -20 >&2 || true
    fi
    ;;
  *.md)
    # No linter; just ensure non-empty.
    if [[ ! -s "$FILE_PATH" ]]; then
      printf 'WARNING: %s is empty\n' "$FILE_PATH" >&2
    fi
    ;;
esac

exit 0

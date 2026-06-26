#!/usr/bin/env bash
# scripts/check-drift.sh — is the packaged plugin behind canonical on the PACKAGED SURFACE?
#
# Read-only. Compares the stamped canonical commit (plugin.json.packagedFrom.commit, with a
# sidecar provenance.json fallback) to canonical HEAD, filtered to the Class-A paths so that
# memory/specs/sessions churn in canonical does not create noise.
#
# Exit: 0 up-to-date / no-packaged-drift · 1 packaged-surface drift (re-cut) · 3 no stamp.
set -euo pipefail

MARKET_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CANONICAL_REPO="${CANONICAL_REPO:-/Users/rohitseelam/Projects/scratchpad-priv}"
PJ="$MARKET_ROOT/plugins/workflow-shell/.claude-plugin/plugin.json"
SIDE="$MARKET_ROOT/plugins/workflow-shell/.claude-plugin/provenance.json"

read_stamp() {
  python3 - "$1" "$2" <<'PY' 2>/dev/null || true
import json, sys
for p in sys.argv[1:]:
    try:
        d = json.load(open(p))
        c = d.get("packagedFrom", {}).get("commit") or d.get("commit")
        if c:
            print(c); break
    except Exception:
        pass
PY
}

STAMP="$(read_stamp "$PJ" "$SIDE")"
[ -n "$STAMP" ] || { echo "DRIFT-UNKNOWN: no packagedFrom stamp (run scripts/repackage.sh)"; exit 3; }

HEAD="$(git -C "$CANONICAL_REPO" rev-parse HEAD)"
if [ "$STAMP" = "$HEAD" ]; then
  echo "UP-TO-DATE: plugin packaged from canonical HEAD ($HEAD)"; exit 0
fi

# Packaged surface = the Class-A canonical paths only.
PATHS=(.claude/agents .claude/constitution.md .claude/rules
       .claude/workflow/README.md .claude/workflow/phases.md .claude/workflow/routing.md
       .claude/workflow/artifacts.md .claude/workflow/communication.md
       .claude/workflow/evaluation.md .claude/workflow/migration.md .claude/workflow/templates
       .claude/skills/workflow .claude/dynamic-workflows/shell-audit.md)

TOTAL="$(git -C "$CANONICAL_REPO" rev-list --count "${STAMP}..${HEAD}" 2>/dev/null || echo '?')"
SURFACE="$(git -C "$CANONICAL_REPO" log --oneline "${STAMP}..${HEAD}" -- "${PATHS[@]}" 2>/dev/null || true)"

echo "Plugin packagedFrom: $STAMP"
echo "Canonical HEAD:      $HEAD  ($TOTAL commits ahead total)"
if [ -z "$SURFACE" ]; then
  echo "NO-PACKAGED-DRIFT: $TOTAL commits ahead but none touch the packaged surface. Re-cut optional."
  exit 0
fi
echo "DRIFT on packaged surface — repackage recommended. Commits since stamp:"
echo "$SURFACE"
exit 1

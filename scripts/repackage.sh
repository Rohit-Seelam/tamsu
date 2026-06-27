#!/usr/bin/env bash
# scripts/repackage.sh — regenerate plugins/workflow-shell/ from canonical .claude/.
#
# Manifest-driven, allow-list, idempotent. Stamps provenance. Does NOT commit.
# Regenerates ONLY the Class-A subtrees (agents, templates, constitution.md, workflow,
# rules, skills, dynamic-workflows). Class-B plugin-native files are preserved untouched:
#   commands/, output-styles/, hooks/, .claude-plugin/ (except the stamper's fields).
#
# Env knobs:
#   CANONICAL_REPO          default /Users/rohitseelam/Projects/scratchpad-priv
#   INCLUDE_STACK_RULES     default true   (ship rules/backend-go.md + frontend-tsx.md)
#   PROMOTE_PROTECT_SECRETS default false  (recorded in provenance; the hook itself is Class-B)
#   PLUGIN_VERSION          default empty  (set e.g. 0.2.0 to bump version this cut)
set -euo pipefail

MARKET_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CANONICAL_REPO="${CANONICAL_REPO:-/Users/rohitseelam/Projects/scratchpad-priv}"
SRC="$CANONICAL_REPO/.claude"
DST="$MARKET_ROOT/plugins/workflow-shell"
LIB="$MARKET_ROOT/scripts/lib"
INCLUDE_STACK_RULES="${INCLUDE_STACK_RULES:-true}"
PROMOTE_PROTECT_SECRETS="${PROMOTE_PROTECT_SECRETS:-false}"
PLUGIN_VERSION="${PLUGIN_VERSION:-}"

[ -d "$SRC" ] || { echo "FATAL: canonical not found at $SRC" >&2; exit 1; }
command -v python3 >/dev/null || { echo "FATAL: python3 required" >&2; exit 1; }

CANON_SHA="$(git -C "$CANONICAL_REPO" rev-parse HEAD)"
CANON_DATE="$(git -C "$CANONICAL_REPO" log -1 --format=%cI HEAD)"
CANON_SUBJECT="$(git -C "$CANONICAL_REPO" log -1 --format=%s HEAD)"
CANON_SPEC="$(git -C "$CANONICAL_REPO" ls-files ".claude/specs" 2>/dev/null \
              | sed -nE 's#^\.claude/specs/([0-9]{3}).*#\1#p' | sort -n | tail -1 || true)"
[ -n "$CANON_SPEC" ] || CANON_SPEC="unknown"
if [ -n "$(git -C "$CANONICAL_REPO" status --porcelain -- .claude 2>/dev/null | head -1)" ]; then
  echo "WARN: canonical .claude has uncommitted changes; stamp records committed HEAD only." >&2
fi

STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT
inject_preamble() { python3 "$LIB/inject_preamble.py" "$1" "$2" "$LIB/agent-preamble.md"; }
copy() { mkdir -p "$(dirname "$2")"; cp "$1" "$2"; }

### Class A — generate into a clean staging tree -------------------------------
# agents (preamble-injected), excluding _template.md
while IFS= read -r f; do
  rel="${f#"$SRC"/agents/}"
  inject_preamble "$f" "$STAGE/agents/$rel"
done < <(find "$SRC/agents" -name '*.md' ! -name '_template.md')

# agent template -> templates/
copy "$SRC/agents/_template.md" "$STAGE/templates/agent-template.md"

# constitution + workflow docs (allow-list)
copy "$SRC/constitution.md" "$STAGE/constitution.md"
for d in README phases routing artifacts communication evaluation migration; do
  copy "$SRC/workflow/$d.md" "$STAGE/workflow/$d.md"
done
[ -d "$SRC/workflow/templates" ] && cp -R "$SRC/workflow/templates" "$STAGE/workflow/templates"

# rules (allow-list; stack rules decision-gated)
for r in general claude-code tests migrations; do copy "$SRC/rules/$r.md" "$STAGE/rules/$r.md"; done
if [ "$INCLUDE_STACK_RULES" = "true" ]; then
  for r in backend-go frontend-tsx; do
    [ -f "$SRC/rules/$r.md" ] && copy "$SRC/rules/$r.md" "$STAGE/rules/$r.md"
  done
fi

# skills: hoist _scripts one level, flatten+prefix verbs, rewrite CLAUDE_SKILL_DIR refs
for p in "$SRC"/skills/workflow/_scripts/*.py; do
  [ -f "$p" ] && copy "$p" "$STAGE/skills/_scripts/$(basename "$p")"
done
for verb in advance new rollback rules-review status; do
  s="$SRC/skills/workflow/$verb/SKILL.md"; [ -f "$s" ] || continue
  mkdir -p "$STAGE/skills/workflow-$verb"
  sed 's#\${CLAUDE_SKILL_DIR}/\.\./_scripts/#${CLAUDE_PLUGIN_ROOT}/skills/_scripts/#g' \
      "$s" > "$STAGE/skills/workflow-$verb/SKILL.md"
done

# dynamic-workflows (md only; exclude runs/)
[ -f "$SRC/dynamic-workflows/shell-audit.md" ] && \
  copy "$SRC/dynamic-workflows/shell-audit.md" "$STAGE/dynamic-workflows/shell-audit.md"

### R1 — refuse to clobber any Class-B path -----------------------------------
for b in commands output-styles hooks .claude-plugin; do
  if [ -e "$STAGE/$b" ]; then
    echo "FATAL: Class-A staging produced a Class-B path '$b' — aborting to avoid clobber." >&2
    exit 1
  fi
done

### Class A -> plugin (replace ONLY generated subtrees) -----------------------
for sub in agents templates constitution.md workflow rules skills dynamic-workflows; do
  rm -rf "${DST:?}/$sub"
done
cp -R "$STAGE/." "$DST/"

### Crux-only contract conditionalization (Deliverable 4 — post-copy transform) ---
# Canonical docs are copied verbatim above; this rewrites them in the plugin so a crux-only
# install (no workflow-memory-pipeline plugin) stops asserting a memory pipeline/guard hook
# it does not ship. Canonical is never touched; this re-applies every cut.
python3 "$LIB/conditionalize_crux.py" "$DST"

### Unmapped report (allow-list residue) --------------------------------------
python3 "$LIB/report_unmapped.py" "$SRC" "$DST" || true

### Provenance stamp ----------------------------------------------------------
STAMP_ARGS=(
  --plugin-json "$DST/.claude-plugin/plugin.json"
  --provenance  "$DST/PROVENANCE.md"
  --sha "$CANON_SHA" --date "$CANON_DATE" --spec "$CANON_SPEC"
  --head-subject "$CANON_SUBJECT"
  --include-stack-rules "$INCLUDE_STACK_RULES"
  --promote-protect-secrets "$PROMOTE_PROTECT_SECRETS"
)
[ -n "$PLUGIN_VERSION" ] && STAMP_ARGS+=(--version "$PLUGIN_VERSION")
python3 "$LIB/stamp_provenance.py" "${STAMP_ARGS[@]}"

echo "Repackaged from canonical $CANON_SHA (spec $CANON_SPEC). Review 'git diff' before committing."

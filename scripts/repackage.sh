#!/usr/bin/env bash
# scripts/repackage.sh — regenerate plugins/workflow-shell/ from canonical .claude/.
#
# Manifest-driven, allow-list, idempotent. Stamps provenance. Does NOT commit.
# Regenerates the Class-A subtrees (agents, templates, constitution.md, workflow, rules, skills,
# dynamic-workflows) and MERGES the Class-A hook surface into hooks/. Purely Class-B plugin-native
# files are preserved untouched: commands/, output-styles/, .claude-plugin/ (except the stamper's
# fields). hooks/ is HYBRID: canonical hook files are merged in, while the plugin-native
# hooks.json + session-context.sh (+ the protect-secrets.sh fork) are preserved.
# A strict report_unmapped gate aborts the cut if any canonical path is unclassified.
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

# Orchestrator path port: its two runtime invocations reference `.claude/hooks/<x>` literally,
# which does not exist in an adopted project (the scripts ship in the PLUGIN's hooks/). Rewrite
# them to the plugin location. The launcher itself is location-independent (env-aware paths),
# but the invoking agent must find it; the session-start context supplies the resolved plugin
# root, and the injected preamble defines the `.claude/hooks/ -> plugin hooks/` mapping.
sed -i '' \
  -e 's#`bash \.claude/hooks/sdk-memory-pipeline\.sh "<active-spec-path>"`#`bash "<plugin-root>/hooks/sdk-memory-pipeline.sh" "<active-spec-path>"` (resolve `<plugin-root>` from the session-start context; run with cwd = the project root)#' \
  -e 's#`\.claude/hooks/detect_batch_intent\.py`#`<plugin-root>/hooks/detect_batch_intent.py`#' \
  "$STAGE/agents/orchestrator.md"

# agent template -> templates/
copy "$SRC/agents/_template.md" "$STAGE/templates/agent-template.md"

# constitution + workflow docs (allow-list)
copy "$SRC/constitution.md" "$STAGE/constitution.md"
for d in README phases routing artifacts communication evaluation migration sdk-pipeline; do
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

# research skill — flatten skills/research/claude-code-docs-fetch/ -> skills/claude-code-docs-fetch/
# (the SHIPPED claude-code-docs agent declares this as its sole tool; nested 2-deep dirs are not
#  discovered as plugin skills, so it must sit one level under skills/).
if [ -d "$SRC/skills/research/claude-code-docs-fetch" ]; then
  for f in "$SRC"/skills/research/claude-code-docs-fetch/*; do
    [ -f "$f" ] && copy "$f" "$STAGE/skills/claude-code-docs-fetch/$(basename "$f")"
  done
fi

# memory skills — flatten skills/memory/<verb>/ -> skills/memory-<verb>/ (read by the SDK pipeline).
for verb in compile extract extraction-learnings jsonl-format; do
  s="$SRC/skills/memory/$verb/SKILL.md"; [ -f "$s" ] || continue
  copy "$s" "$STAGE/skills/memory-$verb/SKILL.md"
done

# hooks — HYBRID. Ship the canonical Class-A hook surface (memory pipeline + its 8 helpers, the
# budget/lint/session hooks) into the plugin's hooks/, MERGED (not clobbered) with the plugin-native
# hooks.json + session-context.sh that have no canonical source. protect-secrets.sh is excluded: the
# plugin carries its own divergent fork (tracked follow-up). Subdirs (tests/, __pycache__) are not
# recursed. NOTE: the sdk_memory_pipeline.py/.sh REPO_ROOT path-resolution is NOT yet ported for the
# plugin location — they ship inert (not wired as settings hooks) pending the memory-runtime step.
for h in "$SRC"/hooks/*.sh "$SRC"/hooks/*.py; do
  [ -f "$h" ] || continue
  base="$(basename "$h")"
  [ "$base" = "protect-secrets.sh" ] && continue
  copy "$h" "$STAGE/hooks/$base"
done

# dynamic-workflows (md only; exclude runs/)
[ -f "$SRC/dynamic-workflows/shell-audit.md" ] && \
  copy "$SRC/dynamic-workflows/shell-audit.md" "$STAGE/dynamic-workflows/shell-audit.md"

# settings.sdk-memory.json — the SDK subprocess's permission settings. Shipped at the plugin ROOT;
# the pipeline resolves it via _asset() (project-side copy wins, else plugin root).
copy "$SRC/settings.sdk-memory.json" "$STAGE/settings.sdk-memory.json"

### Gate — every canonical path must be classified (Class A or C) or the cut ABORTS ----
# The systemic fix from the 2026-06-28 bijective audit: unknown != excluded. Runs on SRC only
# (no DST mutation yet), so a stray/new canonical path fails the build BEFORE the plugin is touched.
python3 "$LIB/report_unmapped.py" "$SRC" --strict

### R1 — refuse to clobber any purely-Class-B path ----------------------------
# hooks/ is intentionally OMITTED: it is now a HYBRID (Class-A canonical hook files merged in
# alongside the plugin-native hooks.json + session-context.sh). The merge below never rm-rf's
# hooks/, so the plugin-native files survive; only same-named files would be overwritten and we
# do not stage hooks.json/session-context.sh/protect-secrets.sh.
for b in commands output-styles .claude-plugin; do
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

# Self-heal the HYBRID hooks/ : the merge above never rm-rf's hooks/, so a hook DELETED or RENAMED in
# canonical would otherwise orphan in the plugin forever (and the SRC-only strict gate cannot see it).
# Prune any DST hook that is neither a freshly-staged canonical hook nor one of the plugin-native files.
NATIVE_HOOKS=("hooks.json" "session-context.sh" "protect-secrets.sh")
if [ -d "$DST/hooks" ]; then
  for existing in "$DST"/hooks/*; do
    [ -f "$existing" ] || continue
    base="$(basename "$existing")"
    keep=false
    for n in "${NATIVE_HOOKS[@]}"; do [ "$base" = "$n" ] && keep=true; done
    [ -e "$STAGE/hooks/$base" ] && keep=true
    if [ "$keep" = false ]; then
      echo "PRUNE orphan hook: hooks/$base (no canonical source, not plugin-native)"
      rm -f "$existing"
    fi
  done
fi

# NOTE: the crux-only conditionalize transform (former Deliverable 4) was RETIRED on 2026-06-28.
# The merged target ships memory in this one plugin, so Rule 5 / the pipeline references are
# unconditionally true — canonical docs are copied verbatim with no banner rewrite.

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

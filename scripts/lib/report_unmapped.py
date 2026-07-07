#!/usr/bin/env python3
"""report_unmapped.py SRC_CANONICAL [DST_PLUGIN] [--strict]

Walk the canonical `.claude/` tree and classify every path as Class A (mapped into the
plugin), Class C (intentionally excluded), or UNMAPPED. UNMAPPED paths are printed so a
new canonical addition can never be silently dropped (the F0-5 failure) or silently leak
in. Allow-list posture: only A + C are "known"; anything else surfaces.

Scope: this is the SRC-side (canonical) half of the bijection — it cannot see a plugin file whose
canonical source was deleted/renamed. The hybrid hooks/ merge's orphan case is reconciled separately
by repackage.sh's hooks/ self-heal prune; transformed Class-A subtrees are fully rm-rf+regenerated.

--strict turns this from an informational report into a BUILD GATE: any UNMAPPED path makes
the script exit non-zero so the cut aborts. This is the fix for the systemic root cause the
2026-06-28 bijective audit found — a hand-maintained allow-list pipeline silently dropped
whatever nobody remembered to name (the memory pipeline, the claude-code-docs-fetch skill,
sdk-pipeline.md). With the gate, **unknown != excluded**: a path is either explicitly MAPPED,
explicitly EXCLUDED (with a reason), or it fails the build.

Both MAPPED and EXCLUDED are deliberately ENUMERATED, not blanketed. The audit's lesson was
that a blanket like `hooks/*` ("plugin ships its own hooks") rots into a silent drop the moment
the target changes. Narrow patterns with reasons are the whole point.

Exit: 0 if no unmapped (or not --strict). 1 if --strict and any unmapped.
"""
import sys
import os
import fnmatch

# Class A — generated into the plugin (with or without transform). Source paths here.
MAPPED = [
    "agents/*.md",                      # fnmatch '*' spans '/', so this covers nested agents
    "agents/_template.md",              # relocated -> templates/agent-template.md
    "constitution.md",
    "rules/general.md", "rules/claude-code.md", "rules/tests.md", "rules/migrations.md",
    "rules/backend-go.md", "rules/frontend-tsx.md",   # stack rules (decision-gated, still classified)
    "workflow/README.md", "workflow/phases.md", "workflow/routing.md",
    "workflow/artifacts.md", "workflow/communication.md", "workflow/evaluation.md",
    "workflow/migration.md",
    "workflow/sdk-pipeline.md",         # authoritative memory-pipeline contract (cited by 9 shipped docs)
    "workflow/templates/*",
    # workflow skills (flattened -> skills/workflow-<verb>/ ; scripts hoisted -> skills/_scripts/)
    "skills/workflow/_scripts/*.py",
    "skills/workflow/advance/SKILL.md", "skills/workflow/new/SKILL.md",
    "skills/workflow/rollback/SKILL.md", "skills/workflow/rules-review/SKILL.md",
    "skills/workflow/status/SKILL.md",
    # research skill (flattened -> skills/claude-code-docs-fetch/) — the claude-code-docs agent's sole tool
    "skills/research/claude-code-docs-fetch/SKILL.md",
    "skills/research/claude-code-docs-fetch/links.json",
    # memory skills (flattened -> skills/memory-<verb>/) — read by the SDK memory pipeline at runtime
    "skills/memory/compile/SKILL.md", "skills/memory/extract/SKILL.md",
    "skills/memory/extraction-learnings/SKILL.md", "skills/memory/jsonl-format/SKILL.md",
    "dynamic-workflows/shell-audit.md",
    # hooks — ENUMERATED Class-A (the merged target ships the full hook surface). Memory pipeline +
    # its 8 helpers + budget/lint/session hooks. Staged into the plugin's hooks/ as a HYBRID merge
    # alongside the plugin-native hooks.json + session-context.sh (which have no canonical source).
    "hooks/sdk_memory_pipeline.py", "hooks/sdk-memory-pipeline.sh",
    "hooks/_actor_map.py", "hooks/_budget_check.py", "hooks/_memory_writer.py",
    "hooks/_orphan_check.py", "hooks/_phase_ledger.py", "hooks/_proposal_schema.py",
    "hooks/_session_scope.py", "hooks/_silo_shape_check.py",
    "hooks/capture-session.sh", "hooks/compile-session.sh",
    "hooks/context-budget-check.py", "hooks/detect_batch_intent.py",
    "hooks/enforce-budget.sh", "hooks/lint-on-write.sh", "hooks/load-active.sh",
    "hooks/memory-write-guard.sh",
]

# Class C — intentionally excluded. NARROW + reasoned (no blanket globs). Per the 2026-06-28 audit.
EXCLUDED = [
    # --- skills not (yet) part of the shell: media is an open product decision (default-excluded) ---
    "skills/media/*",                   # Gemini image-generator; no agent/hook references it (judgment call)
    # --- per-project DATA stores (the OUTPUT of Class-A code; data stays per-project) ---
    "memory/*",                         # memory store written by the (Class-A) SDK pipeline
    "agent-memory/*",                   # per-actor memory silos (data; writer code is Class A)
    "sessions/*",                       # gitignored session-capture data (writer = capture/compile-session.sh)
    "retrospectives/*",                 # per-project retrospective narratives
    "specs/*",                          # per-project spec artifacts (state/spec/tasks + probes)
    "dynamic-workflows/runs/*",         # per-project run logs (the definition shell-audit.md ships)
    "rules/_candidates-*.md",           # transient output of the workflow-rules-review skill
    "workflow/queue.md", "workflow/queue-archive-*.md",   # per-project pre-spec backlog + frozen history
    # --- per-project config (workflow-init seeds fresh; never copied verbatim) ---
    "active.json", "CLAUDE.md",
    "settings.json", "settings.local.json",
    "settings.sdk-memory.json",         # memory allow-list; its CONTENT folds into the init PATCH (not copied)
    # --- the plugin ships its own divergent python fork of protect-secrets.sh; canonical bash copy
    #     is intentionally NOT staged (tracked follow-up: reconcile the fork). Excluded, not MAPPED,
    #     so the gate does not silently treat the canonical<->fork drift as "accounted for". ---
    "hooks/protect-secrets.sh",
    # --- test code/data + build noise (never shipped) ---
    "hooks/tests/*",                    # pytest suite + fixtures (replaces the stale 'hooks/*' blanket)
    "*/__pycache__/*", "__pycache__/*", "*.pyc", "*.pyo",
    "*/.pytest_cache/*", ".pytest_cache/*",   # nested (hooks/.pytest_cache/) AND top-level run cache
    ".venv/*",
    "*/.DS_Store", ".DS_Store",
    ".gitignore", "*/.gitignore",
]


def matches(rel, patterns):
    return any(fnmatch.fnmatch(rel, p) for p in patterns)


def main():
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    strict = "--strict" in sys.argv[1:]
    src = positional[0]
    unmapped = []
    for root, dirs, files in os.walk(src):
        for name in files:
            rel = os.path.relpath(os.path.join(root, name), src)
            rel = rel.replace(os.sep, "/")
            if matches(rel, MAPPED) or matches(rel, EXCLUDED):
                continue
            unmapped.append(rel)
    unmapped.sort()
    if unmapped:
        print("UNMAPPED canonical paths (classify in report_unmapped.py before next cut):")
        for u in unmapped:
            print("  UNMAPPED  %s" % u)
    print("unmapped count: %d" % len(unmapped))
    if unmapped and strict:
        print("FATAL (--strict): %d unmapped canonical path(s). Every canonical path must be explicitly "
              "MAPPED (Class A) or EXCLUDED (Class C, with a reason) — unknown is not the same as excluded. "
              "Classify them, then re-cut." % len(unmapped), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

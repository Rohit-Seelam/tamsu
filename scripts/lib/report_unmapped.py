#!/usr/bin/env python3
"""report_unmapped.py SRC_CANONICAL [DST_PLUGIN]

Walk the canonical `.claude/` tree and classify every path as Class A (mapped into the
plugin), Class C (intentionally excluded), or UNMAPPED. UNMAPPED paths are printed so a
new canonical addition can never be silently dropped (the F0-5 failure) or silently leak
in. Allow-list posture: only A + C are "known"; anything else surfaces.

Exit 0 always (informational). Prints an UNMAPPED count line at the end.
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
    "workflow/templates/*",
    "skills/workflow/_scripts/*.py",
    "skills/workflow/advance/SKILL.md", "skills/workflow/new/SKILL.md",
    "skills/workflow/rollback/SKILL.md", "skills/workflow/rules-review/SKILL.md",
    "skills/workflow/status/SKILL.md",
    "dynamic-workflows/shell-audit.md",
]

# Class C — intentionally excluded (memory pipeline, per-project state, non-crux skills, cruft).
EXCLUDED = [
    "hooks/*",                          # plugin ships its own hooks; canonical hooks excluded
    "workflow/sdk-pipeline.md",
    "workflow/queue.md", "workflow/queue-archive-*.md",
    "settings.sdk-memory.json", "settings.json", "settings.local.json",
    "active.json", "CLAUDE.md",
    "skills/memory/*", "skills/media/*", "skills/research/*",
    "agent-memory/*", "memory/*", "specs/*", "sessions/*", "retrospectives/*",
    "rules/_candidates-*.md",
    "dynamic-workflows/runs/*",
    "*/__pycache__/*", "__pycache__/*", "*.pyc", "*.pyo",
    "*/.DS_Store", ".DS_Store",
    ".gitignore", "*/.gitignore",
    ".venv/*", ".pytest_cache/*",
]


def matches(rel, patterns):
    return any(fnmatch.fnmatch(rel, p) for p in patterns)


def main():
    src = sys.argv[1]
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
        print("UNMAPPED canonical paths (classify in the transform catalog before next cut):")
        for u in unmapped:
            print("  UNMAPPED  %s" % u)
    print("unmapped count: %d" % len(unmapped))


if __name__ == "__main__":
    main()

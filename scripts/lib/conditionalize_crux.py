#!/usr/bin/env python3
"""conditionalize_crux.py PLUGIN_DIR

Deliverable 4 as a POST-COPY transform (approach b). repackage.sh copies the contract docs
verbatim from canonical; this step then rewrites them IN THE PLUGIN so a crux-only install
stops asserting a memory pipeline / guard hook the crux does not ship. Canonical is never
touched, and because repackage re-runs this every cut, the fix can never be clobbered.

Two edit kinds:
  * BANNER — an idempotent crux-only admonition injected at a stable anchor in each
             memory-heavy doc. Drift-proof: it conditionalizes every in-doc memory
             assertion at once, regardless of how canonical re-words the body.
  * ANCHOR — a precise find/replace for a specific false sentence (constitution Rule 5;
             the two one-line memory citations in rules/migrations.md and routing.md).
             Each reports a MISS if its anchor text is absent, so canonical wording drift
             surfaces loudly at re-cut time instead of silently re-introducing a falsehood.

Idempotent (MARKER guard / before-text guard). Prints a summary + a dangling-reference scan.
Exit 0 always; exit-status of the run is judged by the printed MISS count (repackage echoes it).
"""
import os
import sys

MARKER = "<!-- crux-only:conditional (workflow-memory-pipeline absent) -->"

BANNER = MARKER + "\n" + (
    "> **Crux-only note — the `workflow-memory-pipeline` plugin is NOT part of this crux.**\n"
    "> Wherever this document refers to the SDK memory pipeline, `memory-write-guard.sh`,\n"
    "> `workflow/sdk-pipeline.md`, the `agent-memory/` silos, or memory “written at every\n"
    "> `deliver`”, those statements hold **only when the `workflow-memory-pipeline` companion\n"
    "> plugin is installed**. In a default crux-only install there is **no memory writer and no\n"
    "> guard hook**: `deliver` writes no memory, the memory stores are empty or hand-seeded, and\n"
    "> nothing is auto-captured. Treat any memory/pipeline reference below as dormant unless that\n"
    "> plugin is installed.\n"
)

# file -> the exact line (stripped) AFTER which the banner is inserted.
BANNER_TARGETS = {
    "constitution.md": "### 5. Memory hygiene",
    "workflow/README.md": "# Workflow",
    "workflow/phases.md": "# Phases",
    "workflow/evaluation.md": "# Evaluation",
    "workflow/communication.md": "# Communication",
    "workflow/artifacts.md": "# Artifacts",
    "workflow/migration.md": "# Migration",
}

RULE5_BEFORE = (
    "The SDK memory pipeline is the SOLE writer of memory. The orchestrator and every subagent "
    "MUST NOT write `.claude/memory/`, `.claude/agent-memory/`, or the canonical "
    "`~/.claude/projects/<slug>/memory/` — enforced mechanically by "
    "`.claude/hooks/memory-write-guard.sh`. These project instructions override Claude Code's "
    "built-in auto-memory behavior; the auto-memory-disable setting's scope is covered in "
    "`specs/029-memory-sdk-sole-writer/design/auto-load-mechanics.md` (fact 5)."
)

RULE5_AFTER = (
    "This rule's enforcement depends on the `workflow-memory-pipeline` companion plugin.\n\n"
    "**When that plugin is installed:** the SDK memory pipeline is the SOLE writer of memory. "
    "The orchestrator and every subagent MUST NOT write `.claude/memory/`, `.claude/agent-memory/`, "
    "or the canonical `~/.claude/projects/<slug>/memory/` — enforced mechanically by the plugin's "
    "`memory-write-guard.sh` `PreToolUse` hook. These project instructions override Claude Code's "
    "built-in auto-memory behavior.\n\n"
    "**Crux-only — no memory-pipeline plugin installed (the default):** this rule is INERT. There "
    "is no writer and no guard, so nothing is written to the memory roots at `deliver` and decisions "
    "are NOT captured automatically. If a decision is worth retaining, hand-write it into "
    "`.claude/memory/topics/<topic>.md` via a `docs` workflow (permitted because no guard is active). "
    "Do NOT treat a decision as persisted unless the pipeline plugin is installed or you wrote it down "
    "yourself."
)

# file -> (before_substring, after_substring) precise inline replacements.
INLINE = [
    ("rules/migrations.md",
     "We do not write down migrations (decided 2026 — see `memory/topics/conventions.md`).",
     "We do not write down migrations. (This line is the decision of record; a longer rationale lives "
     "in `memory/topics/conventions.md` only when the memory store is populated — i.e. with the "
     "`workflow-memory-pipeline` plugin installed.)"),
    ("workflow/routing.md",
     "top-200 of `memory/MEMORY.md`).",
     "and — if present — the top-200 lines of the canonical "
     "`~/.claude/projects/<slug>/memory/MEMORY.md`). That index is populated only when the "
     "`workflow-memory-pipeline` plugin is installed; in a crux-only install it may be empty or "
     "absent and is simply skipped."),
]

DANGLING_TOKENS = [
    "memory-write-guard.sh", "sdk-pipeline.md", "sdk-memory-pipeline.sh",
    "capture-session.sh", "skills/memory/",
]


def inject_banner(plugin_dir, rel, anchor, report):
    path = os.path.join(plugin_dir, rel)
    if not os.path.isfile(path):
        report["miss"].append("BANNER target missing file: %s" % rel)
        return
    text = open(path, encoding="utf-8").read()
    if MARKER in text:
        return  # idempotent
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if l.strip() == anchor:
            lines[i:i + 1] = [l, "", BANNER.rstrip("\n")]
            open(path, "w", encoding="utf-8").write("\n".join(lines))
            report["banner"].append(rel)
            return
    report["miss"].append("BANNER anchor not found in %s (looked for %r)" % (rel, anchor))


def replace_inline(plugin_dir, rel, before, after, label, report):
    path = os.path.join(plugin_dir, rel)
    if not os.path.isfile(path):
        report["miss"].append("%s target missing file: %s" % (label, rel))
        return
    text = open(path, encoding="utf-8").read()
    if before in text:
        open(path, "w", encoding="utf-8").write(text.replace(before, after, 1))
        report["inline"].append("%s: %s" % (label, rel))
    elif after in text:
        return  # idempotent — already applied
    else:
        report["miss"].append("%s anchor not matched in %s (canonical wording drifted?)" % (label, rel))


def main():
    plugin_dir = sys.argv[1]
    report = {"banner": [], "inline": [], "miss": []}

    for rel, anchor in BANNER_TARGETS.items():
        inject_banner(plugin_dir, rel, anchor, report)

    replace_inline(plugin_dir, "constitution.md", RULE5_BEFORE, RULE5_AFTER, "RULE5", report)
    for rel, before, after in INLINE:
        replace_inline(plugin_dir, rel, before, after, "INLINE", report)

    print("conditionalize-crux: %d banners, %d inline edits, %d MISS"
          % (len(report["banner"]), len(report["inline"]), len(report["miss"])))
    for m in report["miss"]:
        print("  MISS  %s" % m)

    # Informational: dangling references the banners/edits are covering.
    for rel in list(BANNER_TARGETS) + ["workflow/routing.md", "rules/migrations.md"]:
        path = os.path.join(plugin_dir, rel)
        if not os.path.isfile(path):
            continue
        body = open(path, encoding="utf-8").read()
        hits = sum(body.count(tok) for tok in DANGLING_TOKENS)
        if hits:
            print("  refs  %-28s %d dangling pipeline/guard mention(s) (conditionalized)" % (rel, hits))


if __name__ == "__main__":
    main()

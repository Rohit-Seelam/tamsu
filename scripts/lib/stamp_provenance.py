#!/usr/bin/env python3
"""stamp_provenance.py — write canonical lineage into the plugin.

Writes:
  * `plugin.json.packagedFrom` (machine-readable; optionally bumps `version`)
  * a sidecar `.claude-plugin/provenance.json` (same payload; fallback if a loader
    ever strips unknown plugin.json keys — see Deliverable 3 R2)
  * `PROVENANCE.md` (human-readable mirror in the plugin tree)

`packagedFrom.commit` is the CANONICAL commit (not the marketplace commit) — the field
that was absent today (F0-3). With it present, drift is computable:
    git -C <canonical> rev-list --count <packagedFrom.commit>..HEAD
"""
import argparse
import datetime
import json
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugin-json", required=True)
    ap.add_argument("--provenance", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--include-stack-rules", default="true")
    ap.add_argument("--promote-protect-secrets", default="false")
    ap.add_argument("--canonical-repo", default="scratchpad-priv")
    ap.add_argument("--head-subject", default="")
    ap.add_argument("--version", default="")  # optional version bump
    a = ap.parse_args()

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with open(a.plugin_json, encoding="utf-8") as fh:
        pj = json.load(fh)
    if a.version:
        pj["version"] = a.version

    packaged_from = {
        "canonicalRepo": a.canonical_repo,
        "commit": a.sha,
        "committedAt": a.date,
        "canonicalSpec": a.spec,
        "packagedAt": now,
        "packagedBy": "scripts/repackage.sh",
        "options": {
            "includeStackRules": a.include_stack_rules == "true",
            "promoteProtectSecrets": a.promote_protect_secrets == "true",
        },
    }
    pj["packagedFrom"] = packaged_from

    with open(a.plugin_json, "w", encoding="utf-8") as fh:
        json.dump(pj, fh, indent=2)
        fh.write("\n")

    sidecar = os.path.join(os.path.dirname(a.plugin_json), "provenance.json")
    with open(sidecar, "w", encoding="utf-8") as fh:
        json.dump(packaged_from, fh, indent=2)
        fh.write("\n")

    with open(a.provenance, "w", encoding="utf-8") as fh:
        fh.write("# Provenance — workflow-shell\n\n")
        fh.write(
            "This plugin is **generated** from the canonical contract by "
            "`scripts/repackage.sh`. Do not hand-edit generated files (agents, workflow/, "
            "rules/, skills/, constitution.md, templates/, dynamic-workflows/); edit "
            "canonical and re-cut. Plugin-native files (commands/, output-styles/, hooks/, "
            "`.claude-plugin/`) are preserved across re-cuts.\n\n"
        )
        fh.write("| Field | Value |\n|---|---|\n")
        fh.write("| Plugin version | %s |\n" % pj.get("version", "?"))
        fh.write("| Canonical repo | %s |\n" % a.canonical_repo)
        fh.write("| Canonical commit | `%s` |\n" % a.sha)
        fh.write("| Committed at | %s |\n" % a.date)
        fh.write("| Canonical spec | %s |\n" % a.spec)
        fh.write("| Packaged at | %s |\n" % now)
        if a.head_subject:
            fh.write("| HEAD subject | %s |\n" % a.head_subject)
        fh.write("| includeStackRules | %s |\n" % a.include_stack_rules)
        fh.write("| promoteProtectSecrets | %s |\n" % a.promote_protect_secrets)
        fh.write(
            "\nRegenerate with `scripts/repackage.sh` (or `make repackage`). "
            "Check drift against canonical with `scripts/check-drift.sh` (or `make doctor`).\n"
        )

    print("stamped provenance: commit %s, spec %s, version %s"
          % (a.sha, a.spec, pj.get("version")))


if __name__ == "__main__":
    main()

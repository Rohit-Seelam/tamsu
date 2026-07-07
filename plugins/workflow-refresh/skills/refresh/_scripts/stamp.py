#!/usr/bin/env python3
"""stamp.py — read/write .claude/workflow/.workflow-version (the drift keystone).

ONE-writer-per-fact contract shared with /workflow-init: both tools PRESERVE-MERGE this file.
  * workflow-init owns:    adoptedVersion, adoptedAt, lastInitVersion, lastInitAt
  * workflow-refresh owns: refreshedVersion, refreshedSha, refreshedAt, sourceCommit,
                           canonicalSpec, refreshTool, rulesApplied, adoptedSha (set once)
Neither tool deletes the other's keys (dict-copy then update own keys). Path matches what
workflow-init actually writes: .claude/workflow/.workflow-version (NOT .claude/.workflow-version).

Importable: read_stamp(project), write_stamp(project, plugin, applied). Also a CLI.
"""
import argparse
import datetime
import json
import os
import sys

STAMP_REL = os.path.join("workflow", ".workflow-version")
REFRESH_TOOL = "workflow-refresh@0.1.0"


def stamp_path(project):
    return os.path.join(project, ".claude", STAMP_REL)


def read_stamp(project):
    try:
        with open(stamp_path(project)) as fh:
            return json.load(fh)
    except Exception:
        return None


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_stamp(project, plugin, applied=None):
    path = stamp_path(project)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    prev = read_stamp(project) or {}
    now = _now()
    version = plugin.get("version", "unknown")

    out = dict(prev)  # preserve every existing key, including init-owned ones
    out.setdefault("plugin", "workflow-shell@workflow-shell-marketplace")
    out.setdefault("adoptedVersion", version)
    out.setdefault("adoptedAt", now)
    if plugin.get("sha"):
        out.setdefault("adoptedSha", plugin["sha"])

    out["refreshedVersion"] = version
    out["refreshedSha"] = plugin.get("sha")
    out["refreshedAt"] = now
    if plugin.get("provenance") and plugin["provenance"] != "unavailable":
        out["sourceCommit"] = plugin["provenance"]
    if plugin.get("canonicalSpec"):
        out["canonicalSpec"] = plugin["canonicalSpec"]
    out["refreshTool"] = REFRESH_TOOL
    if applied is not None:
        out["rulesApplied"] = applied

    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    ap.add_argument("--plugin", required=True, help="resolve_plugin.py JSON")
    ap.add_argument("--applied", default=None, help="comma-separated rule ids for rulesApplied")
    args = ap.parse_args()
    plugin = json.loads(args.plugin)
    applied = [x for x in args.applied.split(",") if x] if args.applied else None
    out = write_stamp(args.project, plugin, applied)
    print("stamped %s (refreshedVersion %s)" % (stamp_path(args.project), out.get("refreshedVersion")))


if __name__ == "__main__":
    main()

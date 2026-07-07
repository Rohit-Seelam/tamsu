#!/usr/bin/env python3
"""resolve_plugin.py --project PATH

Resolve the CURRENTLY INSTALLED workflow-shell plugin for a project — the moving target refresh
reconciles against. Prints one JSON record to stdout:
  {root, version, sha, provenance, canonicalSpec, memoryPipelineInstalled, source}

Precedence (spec section 2.1):
  1. ~/.claude/plugins/installed_plugins.json -> workflow-shell record whose projectPath == project
     (else a user-scope record, else the first record).
  2. cache glob ~/.claude/plugins/cache/workflow-shell-marketplace/workflow-shell/* (highest semver).
  3. sibling ${CLAUDE_PLUGIN_ROOT}/../../workflow-shell/* (both plugins share the marketplace cache).

Provenance is read from the resolved plugin.json's packagedFrom.{commit,canonicalSpec} (the schema the
repackage stamper writes), with a fallback to top-level source-commit/canonical-spec. Absent -> "unavailable".
This is how refresh stays correct as the package moves: the baseline is whatever is installed right now.
"""
import argparse
import glob
import json
import os
import sys

KEY = "workflow-shell@workflow-shell-marketplace"
MEM_KEY = "workflow-memory-pipeline@workflow-shell-marketplace"
HOME = os.path.expanduser("~")
INSTALLED = os.path.join(HOME, ".claude", "plugins", "installed_plugins.json")
CACHE_GLOB = os.path.join(HOME, ".claude", "plugins", "cache",
                          "workflow-shell-marketplace", "workflow-shell", "*")


def _semver_key(path):
    parts = []
    for p in os.path.basename(path.rstrip("/")).split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(-1)
    return parts


def _load_installed():
    try:
        with open(INSTALLED) as fh:
            return json.load(fh)
    except Exception:
        return None


def _records(data, key):
    if not data:
        return []
    recs = (data.get("plugins", {}) or {}).get(key)
    if recs is None:
        return []
    return recs if isinstance(recs, list) else [recs]


def _pick_record(recs, project):
    rp = os.path.realpath(project) if project else None
    for r in recs:
        pp = r.get("projectPath")
        if pp and os.path.realpath(pp) == rp:
            return r
    for r in recs:
        if r.get("scope") == "user":
            return r
    return recs[0] if recs else None


def _latest(globpat):
    dirs = [d for d in glob.glob(globpat) if os.path.isdir(d)]
    if not dirs:
        return None
    dirs.sort(key=_semver_key)
    return dirs[-1]


def _read_plugin_json(root):
    try:
        with open(os.path.join(root, ".claude-plugin", "plugin.json")) as fh:
            return json.load(fh)
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    args = ap.parse_args()

    data = _load_installed()
    rec = _pick_record(_records(data, KEY), args.project)
    source = root = version = sha = None

    if rec and rec.get("installPath") and os.path.isdir(rec["installPath"]):
        source, root = "installed_plugins", rec["installPath"]
        version, sha = rec.get("version"), rec.get("gitCommitSha")
    if not root:
        c = _latest(CACHE_GLOB)
        if c:
            source, root = "cache", c
    if not root:
        proot = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
        if proot:
            s = _latest(os.path.join(os.path.dirname(os.path.dirname(proot)), "workflow-shell", "*"))
            if s:
                source, root = "sibling", s
    if not root:
        print(json.dumps({"error": "workflow-shell not resolvable", "root": None}))
        return 1

    pj = _read_plugin_json(root)
    packaged = pj.get("packagedFrom") if isinstance(pj.get("packagedFrom"), dict) else {}
    provenance = packaged.get("commit") or pj.get("source-commit") or "unavailable"
    canonical_spec = packaged.get("canonicalSpec") or pj.get("canonical-spec")

    mem = _pick_record(_records(data, MEM_KEY), args.project)
    mem_installed = bool(mem and mem.get("installPath") and os.path.isdir(mem.get("installPath", "")))

    print(json.dumps({
        "root": root,
        "version": pj.get("version", version) or "unknown",
        "sha": sha or packaged.get("commit"),
        "provenance": provenance,
        "canonicalSpec": canonical_spec,
        "memoryPipelineInstalled": mem_installed,
        "source": source,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""detect.py --project P --plugin '<resolve json>' [--applied] | --render

Run every detector against an adopted project and emit the structured drift report (spec section 2.4).
Default: print the JSON report on stdout. --render: read a report JSON from stdin and print a human
summary (so the command renders without re-detecting). This script NEVER writes anything.

The report's "exit" field carries the meaning the command echoes:
  0  no actionable drift            10 actionable drift (dry-run / --check)
  20 residual actionable after apply (use --applied to compute this)
"""
import argparse
import filecmp
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import baseline as _baseline   # noqa: E402
import stamp as _stamp         # noqa: E402

WS_KEY = "workflow-shell@workflow-shell-marketplace"


def _read_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return None


def _perm(settings, kind):
    return list(((settings or {}).get("permissions", {}) or {}).get(kind, []) or [])


def _finding(rule, cls, sev, status, **kw):
    f = {"rule": rule, "class": cls, "severity": sev, "status": status}
    f.update(kw)
    return f


def detect(project, plugin):
    claude = os.path.join(project, ".claude")
    root = plugin.get("root", "") or ""
    bl = _baseline.load_baseline(root)
    findings = []

    # Parse safety: distinguish ABSENT from CORRUPT. If a settings file exists but is unparseable, surface
    # it as a high actionable finding and SKIP every settings-derived rule — reporting those off a wrongly
    # empty {} would both mislead and steer the user straight into a destructive --apply.
    settings, local, parse_errors = {}, {}, []
    try:
        settings = _baseline.load_json_strict(os.path.join(claude, "settings.json")) or {}
    except _baseline.ConfigParseError as e:
        parse_errors.append(os.path.relpath(e.path, project))
    try:
        local = _baseline.load_json_strict(os.path.join(claude, "settings.local.json")) or {}
    except _baseline.ConfigParseError as e:
        parse_errors.append(os.path.relpath(e.path, project))
    settings_ok = not parse_errors
    if parse_errors:
        findings.append(_finding("R-PARSE", "adoption", "high", "manual",
            current=parse_errors, expected="valid JSON settings files",
            action="MANUAL: fix invalid JSON (trailing comma / comment / merge markers); refresh refuses to "
                   "read or write settings until then",
            touchesProjectOwned=True, mode="manual", findingRefs=["F3-1"]))

    # R-STAMP -----------------------------------------------------------------------------------
    st = _stamp.read_stamp(project)
    if not st:
        findings.append(_finding("R-STAMP", "provenance", "medium", "drift",
            current="(absent)", expected="present @ %s" % plugin.get("version"),
            action="write .claude/workflow/.workflow-version", touchesProjectOwned=False,
            mode="auto-safe", findingRefs=["F0-3", "F2-0", "F3-0"]))
    elif st.get("refreshedVersion") != plugin.get("version"):
        findings.append(_finding("R-STAMP", "provenance", "medium", "drift",
            current="refreshedVersion=%s" % st.get("refreshedVersion"),
            expected="refreshedVersion=%s" % plugin.get("version"),
            action="update stamp to installed version", touchesProjectOwned=False,
            mode="auto-safe", findingRefs=["F0-3"]))
    else:
        findings.append(_finding("R-STAMP", "provenance", "low", "clean",
            current="refreshedVersion=%s" % plugin.get("version")))

    # R-SETTINGS / R-STYLE / R-SEC / R-SEC-ALLOW — only meaningful when settings parsed ----------
    if settings_ok:
        exp = bl["settings_expected"] or {}
        miss = []
        if exp.get("outputStyle") and not settings.get("outputStyle"):
            miss.append("outputStyle")                          # absent -> auto-safe drift
        ep = settings.get("enabledPlugins") or {}
        if WS_KEY not in ep:                                    # membership: an explicit `false` is respected
            miss.append("enabledPlugins[%s]" % WS_KEY)
        cur_sub = settings.get("subagents") or {}
        for k, v in (exp.get("subagents") or {}).items():
            if k not in cur_sub:
                miss.append("subagents.%s" % k)
            elif isinstance(cur_sub.get(k), dict):              # detect stale skills lists, not just absent keys
                cur_sk = cur_sub[k].get("skills", []) or []
                add = [x for x in ((v or {}).get("skills", []) or []) if x not in cur_sk]
                if add:
                    miss.append("subagents.%s.skills+=%s" % (k, add))
        if miss:
            findings.append(_finding("R-SETTINGS", "adoption", "medium", "drift",
                current=miss, expected="settings superset of expected keys + subagent skills",
                action="deep-merge expected settings (set-missing keys; union subagent skills; never "
                       "overwrite a user value)",
                touchesProjectOwned=False, mode="auto-safe", findingRefs=["F18-4", "F16-2"]))
        else:
            findings.append(_finding("R-SETTINGS", "adoption", "low", "clean"))

        # A deliberately-overridden outputStyle is an acknowledged user choice, NOT actionable drift.
        if exp.get("outputStyle") and settings.get("outputStyle") and settings.get("outputStyle") != exp["outputStyle"]:
            findings.append(_finding("R-STYLE", "adoption", "info", "info",
                current=settings.get("outputStyle"), expected=exp.get("outputStyle"),
                action="INFO: project overrides outputStyle; left as-is (acknowledged override)",
                touchesProjectOwned=True, mode="info", findingRefs=["F18-4"]))

        # R-SEC — local-only deny entries should be migrated up to the committed file, so they count as drift.
        committed = _perm(settings, "deny")
        localdeny = _perm(local, "deny")
        expected_deny = bl["deny"]
        missing = [d for d in expected_deny if d not in committed]
        only_local = [d for d in localdeny if d not in committed]
        if missing or only_local:
            bits = []
            if missing:
                bits.append("%d baseline" % len(missing))
            if only_local:
                bits.append("%d local-only" % len(only_local))
            findings.append(_finding("R-SEC", "secrets-protection", "high", "drift",
                current=committed, expected=sorted(set(expected_deny) | set(localdeny)),
                action="union missing deny entries (%s) into .claude/settings.json" % " + ".join(bits),
                touchesProjectOwned=False, mode="auto-safe",
                detail=("migrating %d deny entr(ies) up from settings.local.json" % len(only_local)) if only_local else "",
                findingRefs=["F0-0", "F4-7", "F8-2", "F11-2", "F12-2", "F16-3"]))
        else:
            findings.append(_finding("R-SEC", "secrets-protection", "low", "clean",
                current="committed deny superset of baseline + local"))

        # R-SEC-ALLOW (manual warn)
        broad = [a for a in (_perm(settings, "allow") + _perm(local, "allow")) if _baseline.is_broad_allow(a)]
        if broad:
            findings.append(_finding("R-SEC-ALLOW", "secrets-protection", "medium", "manual",
                current=broad, expected="no Read(*)/Write(*)/bare Bash allow",
                action="WARN: scope these allow entries (cannot auto-narrow user intent)",
                touchesProjectOwned=False, mode="manual", findingRefs=["F16-4"]))

    # R-SEC-HOOK (info; package concern) --------------------------------------------------------
    htext = ""
    try:
        with open(os.path.join(root, "hooks", "hooks.json")) as fh:
            htext = fh.read()
    except Exception:
        pass
    if "protect-secrets" not in htext:
        findings.append(_finding("R-SEC-HOOK", "secrets-protection", "info", "info",
            current="installed package has no protect-secrets.sh PreToolUse hook",
            expected="runtime secrets guard present",
            action="INFO: deny-list is the only defense; upgrade workflow-shell for the guard hook",
            touchesProjectOwned=False, mode="info", findingRefs=["F0-0"]))

    # R-COPY ------------------------------------------------------------------------------------
    copies = []
    for rel in bl["copy_artifacts"]:
        ppath = os.path.join(claude, rel)
        if not os.path.exists(ppath):
            continue
        src = os.path.join(root, rel)
        matched = os.path.isfile(ppath) and os.path.isfile(src) and filecmp.cmp(ppath, src, shallow=False)
        copies.append({"path": ".claude/%s" % rel, "byteMatched": bool(matched), "isDir": os.path.isdir(ppath)})
    if copies:
        all_matched = all(c["byteMatched"] for c in copies)
        findings.append(_finding("R-COPY", "copy-duplicate", "medium",
            "drift" if all_matched else "manual",
            current=[c["path"] for c in copies], expected="no plugin-owned copies in project",
            action="rm byte-matched plugin copies; divergent copies / directories are manual",
            touchesProjectOwned=False, mode="auto-safe" if all_matched else "manual",
            detail=copies, findingRefs=["F7-3"]))
    else:
        findings.append(_finding("R-COPY", "copy-duplicate", "low", "clean"))

    # R-WORKTREE (manual warn) — duplicated .claude/ inside a git worktree -----------------------
    gitpath = os.path.join(project, ".git")
    in_worktree = False
    if os.path.isfile(gitpath):                       # a linked worktree/submodule has .git as a FILE
        try:
            in_worktree = "worktrees/" in open(gitpath, encoding="utf-8").read()
        except Exception:
            in_worktree = False
    if in_worktree and (os.path.isdir(os.path.join(claude, "agents")) or os.path.isdir(os.path.join(claude, "commands"))):
        findings.append(_finding("R-WORKTREE", "copy-duplicate", "low", "manual",
            current=".claude/{agents,commands} duplicated inside a git worktree",
            expected="single source of truth (no duplicated .claude in a worktree)",
            action="WARN: de-dup .claude/ in this worktree (manual — it may hold active work)",
            touchesProjectOwned=True, mode="manual", findingRefs=["F7-3"]))

    # R-STATE (opt-in) --------------------------------------------------------------------------
    schema = bl["state_schema"] or {}
    required = schema.get("required", [])
    legacy_map = schema.get("legacyMap", {})
    bad = []
    for sp in sorted(glob.glob(os.path.join(claude, "specs", "*", "state.json"))):
        d = _read_json(sp) or {}
        missing_keys = [k for k in required if k not in d]
        legacy = [lk for lk, nk in legacy_map.items() if lk in d and nk not in d]   # only while target absent
        if missing_keys or legacy:
            bad.append({"path": os.path.relpath(sp, project), "missing": missing_keys, "legacy": legacy})
    if bad:
        findings.append(_finding("R-STATE", "state-schema", "low", "drift",
            current=bad, expected="state.json superset of required keys",
            action="normalize (add missing keys; map legacy) — opt-in --migrate-state",
            touchesProjectOwned=True, mode="opt-in", findingRefs=["F2-1"]))

    # R-CRUFT / R-ORPHAN-HOOK (opt-in) — settings-derived ---------------------------------------
    if settings_ok:
        cruft = [a for a in _perm(local, "allow") if _baseline.is_cruft_allow(a)]
        if cruft:
            findings.append(_finding("R-CRUFT", "local-cruft", "low", "drift",
                current=cruft, expected="no cruft-signature allow entries",
                action="strip cruft from settings.local.json — opt-in --strip-cruft",
                touchesProjectOwned=False, mode="opt-in", findingRefs=["F3-2"]))

        orphan = _orphan_hooks(settings, project) + _orphan_hooks(local, project)
        if orphan:
            findings.append(_finding("R-ORPHAN-HOOK", "local-cruft", "low", "drift",
                current=orphan, expected="hook targets exist",
                action="prune orphaned hook reminders — opt-in --strip-cruft",
                touchesProjectOwned=True, mode="opt-in", findingRefs=["F17-5"]))

    # R-CLAUDEMD (manual) -----------------------------------------------------------------------
    cmtext = ""
    try:
        with open(os.path.join(claude, "CLAUDE.md"), encoding="utf-8") as fh:
            cmtext = fh.read()
    except Exception:
        pass
    hits = [p for p in _baseline.PLACEHOLDERS if p in cmtext]
    if hits:
        findings.append(_finding("R-CLAUDEMD", "placeholder", "medium", "manual",
            current=hits, expected="de-placeholdered CLAUDE.md",
            action="MANUAL: fill the one-line description and ## Stack (never auto-authored)",
            touchesProjectOwned=True, mode="manual", findingRefs=["F3-1"]))

    # R-MEM-DOC (info) --------------------------------------------------------------------------
    if not plugin.get("memoryPipelineInstalled"):
        findings.append(_finding("R-MEM-DOC", "memory-doc", "info", "info",
            current="workflow-memory-pipeline not installed",
            expected="memory/pipeline assertions are dormant (honor-system Rule 5)",
            action="INFO: nothing auto-written at deliver; hand-write decisions or install the companion plugin",
            touchesProjectOwned=False, mode="info", findingRefs=["F0-1", "F0-2", "F1-0"]))

    return findings


def _orphan_hooks(settings, project):
    hooks = (settings or {}).get("hooks", {})
    if not hooks:
        return []
    if "MEMORY.md" in json.dumps(hooks):
        if not glob.glob(os.path.join(project, "**", "MEMORY.md"), recursive=True):
            return ["hook references MEMORY.md but none found under project"]
    return []


def summarize(findings):
    s = {"high": 0, "medium": 0, "low": 0, "info": 0, "clean": 0}
    for f in findings:
        if f["status"] == "clean":
            s["clean"] += 1
        else:
            s[f["severity"]] = s.get(f["severity"], 0) + 1
    return s


def compute_exit(findings, applied=False):
    actionable = [f for f in findings
                  if f["status"] in ("drift", "manual") and f["severity"] in ("high", "medium")]
    if not actionable:
        return 0
    return 20 if applied else 10


def build_report(project, plugin, applied=False):
    findings = detect(project, plugin)
    return {
        "project": os.path.realpath(project),
        "adopted": os.path.isfile(os.path.join(project, ".claude", "active.json")),
        "plugin": {
            "version": plugin.get("version"), "sha": plugin.get("sha"),
            "provenance": plugin.get("provenance"), "canonicalSpec": plugin.get("canonicalSpec"),
            "source": plugin.get("source"), "memoryPipelineInstalled": plugin.get("memoryPipelineInstalled"),
        },
        "stampPresent": _stamp.read_stamp(project) is not None,
        "summary": summarize(findings),
        "findings": findings,
        "exit": compute_exit(findings, applied=applied),
    }


_GLYPH = {"clean": "ok ", "drift": "DRIFT", "manual": "MANUAL", "info": "info"}


def render(report):
    p = report["plugin"]
    prov = p.get("provenance") or "unavailable"
    prov_s = ("canonical %s (spec %s)" % (prov[:9], p.get("canonicalSpec"))) if prov != "unavailable" else "unavailable"
    out = []
    out.append("workflow-refresh — drift report")
    out.append("  project : %s" % report["project"])
    out.append("  plugin  : workflow-shell %s  [%s]  provenance: %s"
               % (p.get("version"), p.get("source"), prov_s))
    out.append("  stamp   : %s" % ("present" if report["stampPresent"] else "ABSENT (never refreshed)"))
    s = report["summary"]
    out.append("  summary : high=%d medium=%d low=%d info=%d clean=%d"
               % (s["high"], s["medium"], s["low"], s["info"], s["clean"]))
    out.append("")
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    rows = [f for f in report["findings"] if f["status"] != "clean"]
    rows.sort(key=lambda f: order.get(f["severity"], 9))
    if not rows:
        out.append("  no drift — project is in sync with the installed plugin.")
    for f in rows:
        tag = _GLYPH.get(f["status"], f["status"])
        owned = " [project-owned → manual]" if f.get("touchesProjectOwned") and f["mode"] != "auto-safe" else ""
        out.append("  [%-6s] %-13s %-9s %s%s" % (tag, f["rule"], f["severity"], f.get("action", ""), owned))
        if f.get("detail"):
            d = f["detail"]
            out.append("           detail: %s" % (d if isinstance(d, str) else json.dumps(d)))
    out.append("")
    out.append("  exit: %d  (0 clean · 10 drift · 20 residual-after-apply)" % report["exit"])
    print("\n".join(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    ap.add_argument("--plugin", help="resolve_plugin.py JSON")
    ap.add_argument("--applied", action="store_true", help="compute residual (post-apply) exit code")
    ap.add_argument("--render", action="store_true", help="read a report JSON from stdin and pretty-print")
    args = ap.parse_args()

    if args.render:
        render(json.load(sys.stdin))
        return 0

    plugin = json.loads(args.plugin) if args.plugin else {}
    print(json.dumps(build_report(args.project, plugin, applied=args.applied)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

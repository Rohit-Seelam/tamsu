#!/usr/bin/env python3
"""repair.py --project P --plugin '<resolve json>' --report '<detect json>' [flags]

Apply idempotent, mode-gated repairs. Order (spec section 3.2):
  R-COPY -> R-SETTINGS -> R-SEC -> (opt-in R-STATE, R-CRUFT, R-ORPHAN-HOOK) -> R-STAMP (last, always).

Invariants enforced here:
  * Additive settings merge — union deny / set-missing keys; never delete or overwrite a user value.
  * Byte-match gate for deletions — a copy is removed only if it byte-matches the installed plugin file.
  * Project-owned files (state.json, settings.local.json) only with their explicit flag.
  * Every mutation journaled into .workflow-version.rulesApplied via stamp.write_stamp (R-STAMP).

Flags: --apply (required to write), --migrate-state, --strip-cruft, --only=R-A,R-B
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


def _load(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return None


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def repair_copy(claude, root, copy_artifacts):
    removed = []
    for rel in copy_artifacts:
        ppath = os.path.join(claude, rel)
        if not os.path.exists(ppath):
            continue
        src = os.path.join(root, rel)
        if os.path.isfile(ppath) and os.path.isfile(src) and filecmp.cmp(ppath, src, shallow=False):
            os.remove(ppath)
            removed.append(".claude/%s" % rel)
        # directories and divergent files are left for manual handling (never auto-deleted)
    return removed


def repair_settings(claude, exp):
    path = os.path.join(claude, "settings.json")
    s = _baseline.load_json_strict(path) or {}     # strict: never coerce a corrupt file to {}
    changed = False
    if exp.get("outputStyle") and not s.get("outputStyle"):
        s["outputStyle"] = exp["outputStyle"]      # set-missing only; a user's override is left untouched
        changed = True
    if exp.get("enabledPlugins"):
        ep = s.setdefault("enabledPlugins", {})
        for k, v in exp["enabledPlugins"].items():
            if k not in ep:                        # membership, not truthiness: keep an explicit `false`
                ep[k] = v
                changed = True
    if exp.get("subagents"):
        sub = s.setdefault("subagents", {})
        for k, v in exp["subagents"].items():
            if k not in sub:
                sub[k] = v
                changed = True
            elif isinstance(sub.get(k), dict) and isinstance(v, dict):
                cur_sk = sub[k].get("skills", []) or []
                add = [x for x in (v.get("skills", []) or []) if x not in cur_sk]
                if add:                            # union-merge new skills additively (preserve order)
                    sub[k]["skills"] = cur_sk + add
                    changed = True
    if changed:
        _write_json(path, s)
    return changed


def repair_sec(claude, expected_deny, local_deny=None):
    path = os.path.join(claude, "settings.json")
    s = _baseline.load_json_strict(path) or {}     # strict: never coerce a corrupt file to {}
    perms = s.setdefault("permissions", {})
    cur = perms.get("deny", []) or []
    # union committed + broadened baseline + any deny living only in settings.local.json (migrate up).
    new = sorted(set(cur) | set(expected_deny) | set(local_deny or []))
    if set(new) != set(cur):                       # semantic change only -> idempotent re-apply
        perms["deny"] = new
        _write_json(path, s)
        return True
    return False


def repair_orphan(project):
    """Prune hook entries that reference a MEMORY.md which does not exist under the project."""
    claude = os.path.join(project, ".claude")
    if glob.glob(os.path.join(project, "**", "MEMORY.md"), recursive=True):
        return []                                  # target exists -> not orphaned
    pruned = []
    for fname in ("settings.json", "settings.local.json"):
        path = os.path.join(claude, fname)
        s = _baseline.load_json_strict(path)
        if not s or "hooks" not in s:
            continue
        hooks = s["hooks"]
        changed = False
        for ev in list(hooks.keys()):
            arr = hooks.get(ev)
            if not isinstance(arr, list):
                continue
            kept = [g for g in arr if "MEMORY.md" not in json.dumps(g)]
            if len(kept) != len(arr):
                changed = True
                pruned.append("%s:%s" % (fname, ev))
                if kept:
                    hooks[ev] = kept
                else:
                    del hooks[ev]
        if changed:
            if not hooks:
                del s["hooks"]
            _write_json(path, s)
    return pruned


def repair_state(claude, schema):
    required = schema.get("required", [])
    legacy_map = schema.get("legacyMap", {})
    defaults = schema.get("defaults", {})
    touched = []
    for sp in glob.glob(os.path.join(claude, "specs", "*", "state.json")):
        d = _load(sp)
        if d is None:
            continue
        before = json.dumps(d, sort_keys=True)
        for lk, nk in legacy_map.items():
            if lk in d and nk not in d:
                d[nk] = d[lk]                  # map legacy -> current, KEEP original key
        for k in required:
            if k not in d and k in defaults:
                d[k] = defaults[k]             # only fill keys we have a safe default for
        if json.dumps(d, sort_keys=True) != before:
            tags = d.setdefault("tags", [])
            if "legacy-normalized" not in tags:
                tags.append("legacy-normalized")
            _write_json(sp, d)
            touched.append(os.path.relpath(sp, claude))
    return touched


def repair_cruft(claude):
    path = os.path.join(claude, "settings.local.json")
    s = _load(path)
    if not s:
        return []
    allow = (s.get("permissions", {}) or {}).get("allow", []) or []
    removed = [a for a in allow if _baseline.is_cruft_allow(a)]
    if removed:
        s["permissions"]["allow"] = [a for a in allow if not _baseline.is_cruft_allow(a)]
        _write_json(path, s)
    return removed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    ap.add_argument("--plugin", required=True)
    ap.add_argument("--report", default="")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--migrate-state", action="store_true")
    ap.add_argument("--strip-cruft", action="store_true")
    ap.add_argument("--only", default="")
    # tolerate the other passthrough flags the command forwards (no-ops here)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    args, _unknown = ap.parse_known_args()

    plugin = json.loads(args.plugin)
    project = args.project
    claude = os.path.join(project, ".claude")
    root = plugin.get("root", "") or ""
    bl = _baseline.load_baseline(root)
    only = set(x.strip() for x in args.only.split(",") if x.strip()) or None

    def want(rule):
        return only is None or rule in only

    if not args.apply:
        print("repair.py: --apply not set; no writes performed.")
        return 0

    # Pre-flight: a settings file that EXISTS but is unparseable must abort the whole apply BEFORE any
    # write — never overwrite hand-edited / merge-conflicted config and silently wipe it (and its deny rules).
    local_deny = []
    for fname in ("settings.json", "settings.local.json"):
        try:
            loaded = _baseline.load_json_strict(os.path.join(claude, fname))
        except _baseline.ConfigParseError as e:
            print("ABORT: %s exists but is not valid JSON — refusing to write." % e.path)
            print("       Fix the file's JSON, then re-run. No files were modified.")
            return 1
        if fname == "settings.local.json":
            local_deny = ((loaded or {}).get("permissions", {}) or {}).get("deny", []) or []

    applied = []

    if want("R-COPY"):
        rm = repair_copy(claude, root, bl["copy_artifacts"])
        if rm:
            applied.append("R-COPY")
            print("R-COPY: removed %d byte-matched plugin copies" % len(rm))
    if want("R-SETTINGS"):
        if repair_settings(claude, bl["settings_expected"] or {}):
            applied.append("R-SETTINGS")
            print("R-SETTINGS: merged missing expected settings keys / subagent skills")
    if want("R-SEC"):
        if repair_sec(claude, bl["deny"], local_deny):
            applied.append("R-SEC")
            print("R-SEC: unioned broadened (+ migrated local-only) deny-list into settings.json")
    if args.migrate_state and want("R-STATE"):
        t = repair_state(claude, bl["state_schema"] or {})
        if t:
            applied.append("R-STATE")
            print("R-STATE: normalized %d state.json file(s): %s" % (len(t), ", ".join(t)))
    if args.strip_cruft and want("R-CRUFT"):
        c = repair_cruft(claude)
        if c:
            applied.append("R-CRUFT")
            print("R-CRUFT: stripped %d cruft allow entr(ies) from settings.local.json" % len(c))
    if args.strip_cruft and want("R-ORPHAN-HOOK"):
        o = repair_orphan(project)
        if o:
            applied.append("R-ORPHAN-HOOK")
            print("R-ORPHAN-HOOK: pruned %d orphaned hook reminder(s): %s" % (len(o), ", ".join(o)))

    # R-STAMP — always last and always runs on --apply (the provenance keystone; it is not subject to
    # --only filtering, per the rule table). It skips the WRITE on a fully-converged re-apply (nothing
    # repaired AND stamp already at the installed version) so a no-change second --apply is a true no-op
    # with zero mtime churn (acceptance criterion 8).
    st = _stamp.read_stamp(project)
    stamp_current = bool(st) and st.get("refreshedVersion") == plugin.get("version")
    if applied or not stamp_current:
        _stamp.write_stamp(project, plugin, applied=applied + ["R-STAMP"])
        print("R-STAMP: wrote .claude/workflow/.workflow-version (rulesApplied=%s)" % (applied + ["R-STAMP"]))
    else:
        print("R-STAMP: stamp already current and nothing repaired; no write")
    print("applied: %s" % (applied + ["R-STAMP"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

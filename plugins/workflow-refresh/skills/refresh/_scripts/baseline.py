#!/usr/bin/env python3
"""baseline.py — load the EXPECTED baseline for the comparisons refresh makes.

Precedence per field (first hit wins), per the workflow-refresh spec section 4.2:
  1. $PLUGIN_ROOT/baseline/*            authoritative; a future repackage cut adds these so the
                                        plugin self-describes what an adopted project should look like.
  2. parse PATCH='...' in $PLUGIN_ROOT/commands/workflow-init.md   (works against today's package).
  3. this plugin's bundled baseline/    refresh defaults; the only source of the BROADENED secrets superset.

For secrets, expected = union(installed_expected_deny, bundled_broadened_deny). Union-only: an old narrow
package still gets defense-in-depth and nothing a project already denies is ever removed.

Also the single source of truth for the local-cruft / broad-allow / placeholder signatures, imported by
both detect.py and repair.py so a detector and its repair can never disagree about what they match.

Importable: load_baseline(plugin_root) -> dict. Also a CLI for debugging.
"""
import json
import os
import re
import sys

BUNDLED = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "baseline"))

# ---- shared signatures (one source of truth for detect + repair) ------------------------------
PLACEHOLDERS = [
    "<one-line description — EDIT THIS>",      # em-dash, matches the seeded CLAUDE.md exactly
    "EDIT: languages, frameworks, entry points",
]
_BROAD_ALLOW = re.compile(r"^(Read|Write|Edit)\(\*\)$|^Bash$|^Bash\(\*\)$")


def is_broad_allow(entry):
    return bool(_BROAD_ALLOW.match((entry or "").strip()))


def is_cruft_allow(entry):
    """Known local-cruft allow signatures (R-CRUFT): doubled-slash paths and one-off
    python3 plugin/marketplace introspection allows. Conservative — matches only these."""
    s = (entry or "").strip()
    if "(//" in s:                                   # e.g. Read(//Users/...) doubled slash
        return True
    if s.startswith("Bash(python3 -c") and ("plugin" in s or "market" in s):
        return True
    return False


# ---- safe config loading (absent vs. corrupt) -------------------------------------------------
class ConfigParseError(Exception):
    """Raised when a config file EXISTS and is non-empty but cannot be parsed as JSON. The caller must
    NEVER overwrite such a file — doing so would silently destroy hand-edited / merge-conflicted config."""

    def __init__(self, path, cause=None):
        self.path = path
        self.cause = cause
        super().__init__("present but unparseable JSON: %s (%s)" % (path, cause))


def load_json_strict(path):
    """Return {} if the file is absent or empty; the parsed object if valid; raise ConfigParseError if the
    file is present and non-empty but not parseable. This is the one loader any code that WRITES a config
    file must use, so 'file absent' is never confused with 'file present but corrupt' (the latter must abort,
    not be coerced to {} and overwritten)."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except Exception as e:
        raise ConfigParseError(path, e)


# ---- baseline loading -------------------------------------------------------------------------
def _read_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return None


def _read_lines(path):
    try:
        with open(path) as fh:
            return [l.strip() for l in fh if l.strip() and not l.lstrip().startswith("#")]
    except Exception:
        return None


def _parse_init_patch(plugin_root):
    """Extract the PATCH='{...}' JSON literal from the installed workflow-init.md (one line)."""
    p = os.path.join(plugin_root, "commands", "workflow-init.md")
    try:
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
    except Exception:
        return None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("PATCH='") and s.endswith("'"):
            try:
                return json.loads(s[len("PATCH='"):-1])
            except Exception:
                return None
    return None


def load_baseline(plugin_root):
    pb = os.path.join(plugin_root or "", "baseline")

    plugin_deny = _read_json(os.path.join(pb, "secrets.deny.json"))
    plugin_settings = _read_json(os.path.join(pb, "settings.expected.json"))
    plugin_copy = _read_lines(os.path.join(pb, "copy-artifacts.txt"))
    plugin_state = _read_json(os.path.join(pb, "state-schema.json"))

    patch = _parse_init_patch(plugin_root or "")
    init_deny = (patch or {}).get("permissions", {}).get("deny") if patch else None
    init_settings = {k: v for k, v in patch.items() if k != "permissions"} if patch else None

    bundled_deny = _read_json(os.path.join(BUNDLED, "secrets.deny.json")) or []
    bundled_settings = _read_json(os.path.join(BUNDLED, "settings.expected.json")) or {}
    bundled_copy = _read_lines(os.path.join(BUNDLED, "copy-artifacts.txt")) or []
    bundled_state = _read_json(os.path.join(BUNDLED, "state-schema.json")) or {}

    settings_expected = plugin_settings or init_settings or bundled_settings
    installed_deny = plugin_deny if plugin_deny is not None else (init_deny or [])
    deny = sorted(set(installed_deny) | set(bundled_deny))   # union-only, never subtract
    copy_artifacts = plugin_copy if plugin_copy is not None else bundled_copy
    state_schema = plugin_state or bundled_state

    return {
        "deny": deny,
        "settings_expected": settings_expected,
        "copy_artifacts": copy_artifacts,
        "state_schema": state_schema,
        "_sources": {
            "deny": "plugin" if plugin_deny is not None else ("init-patch" if init_deny else "bundled"),
            "settings": "plugin" if plugin_settings else ("init-patch" if init_settings else "bundled"),
        },
    }


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WORKFLOW_SHELL_ROOT", "")
    print(json.dumps(load_baseline(root), indent=2))

#!/usr/bin/env bash
# hooks/protect-secrets.sh — PreToolUse secrets guard (workflow-shell plugin).
#
# Blocks Claude from reading, editing, writing, or shelling at known secret files
# (.env*, credentials.json, service-account*.json, SSH private keys) for BOTH file
# tools AND Bash commands. Exit 2 = block (Claude sees stderr as feedback). Exit 0 = allow.
#
# Ported from canonical .claude/hooks/protect-secrets.sh to drop the `jq` dependency:
# the crux standardizes on python3 (same as session-context.sh), and a security hook must
# NOT fail-open when a tool is missing. Registered in hooks.json under PreToolUse via
# ${CLAUDE_PLUGIN_ROOT}; project-agnostic (judges the tool's target, not a project file).
#
# Input: tool-call JSON on stdin (.tool_name, .tool_input.file_path, .tool_input.command).
exec python3 -c '
import sys, os, re
try:
    d = __import__("json").loads(sys.stdin.read())
except Exception:
    sys.exit(0)
tool = d.get("tool_name", "") or ""
ti = d.get("tool_input") or {}

# Matches: .env, .env.local/.production/.<anything>, credentials.json,
# service-account*.json, id_rsa/id_ed25519/id_ecdsa[.pub].
PROTECTED = re.compile(r"^(\.env(\.[A-Za-z0-9_-]+)?|credentials\.json|service-account.*\.json|id_(rsa|ed25519|ecdsa)(\.pub)?)$")
# Allow-list for known-safe templates, checked first to short-circuit.
ALLOW = re.compile(r"^\.env\.(example|sample|template|dist|defaults?)$")
# Bash: the same basenames as a separate token (boundary chars before/after).
BASHTOK = re.compile(r"(^|[\s/;&|\"`(])(\.env(\.[A-Za-z0-9_-]+)?|credentials\.json|service-account.*\.json|id_(rsa|ed25519|ecdsa)(\.pub)?)([\s/;&|\"`)]|$)")

def block(msg):
    sys.stderr.write("BLOCKED by hooks/protect-secrets.sh — %s\n" % msg)
    sys.stderr.write("Reason: this access targets a protected secret file.\n")
    sys.stderr.write("If a script needs the value, load it via os.getenv / process.env so Claude never sees the file contents.\n")
    sys.stderr.write("To extend or relax this list, edit PROTECTED in this hook.\n")
    sys.exit(2)

if tool in ("Read", "Edit", "MultiEdit", "Write"):
    fp = ti.get("file_path", "") or ""
    if not fp:
        sys.exit(0)
    base = os.path.basename(fp)
    if ALLOW.match(base):
        sys.exit(0)
    if PROTECTED.match(base):
        block("%s on %s" % (tool, fp))
elif tool == "Bash":
    cmd = ti.get("command", "") or ""
    if not cmd:
        sys.exit(0)
    if BASHTOK.search(cmd):
        block("Bash references a protected secret: %s" % cmd)

sys.exit(0)
'

#!/usr/bin/env bash
set -euo pipefail

# Path resolution (env-aware, plugin-portable):
#   REPO_ROOT    = the PROJECT the pipeline writes memory FOR. $CLAUDE_PROJECT_DIR when the harness
#                  provides it; else the historical two-levels-up (true when this file lives at
#                  <repo>/.claude/hooks/); else $PWD (orchestrator runs us with cwd = project root).
#   ENTRY_SCRIPT = always our sibling sdk_memory_pipeline.py (location-independent — works from
#                  canonical .claude/hooks/ AND from the plugin's hooks/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then
    REPO_ROOT="$(cd "${CLAUDE_PROJECT_DIR}" && pwd)"
elif [[ "${SCRIPT_DIR}" == */.claude/hooks ]]; then
    REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
else
    REPO_ROOT="$(pwd)"
fi
VENV_PYTHON="${REPO_ROOT}/.claude/.venv/bin/python"
ENTRY_SCRIPT="${SCRIPT_DIR}/sdk_memory_pipeline.py"
LOCK_DIR="${REPO_ROOT}/.claude/sessions"
LOCK_FILE="${LOCK_DIR}/.sdk-memory.lock"
# LOG_DIR holds the run logs AND the gitignored spend markers (_last-run.json,
# _spend-total.json). SDK_MEMORY_LOG_DIR lets a test (or the smoke path) redirect
# both into a tmp tree so a non-real run never writes the real markers.
LOG_DIR="${SDK_MEMORY_LOG_DIR:-${REPO_ROOT}/.claude/sessions/sdk-memory}"
LOG_PATH=""
# WHOLE-RUN wall-clock budget (spec 038 M6, decision 2). The propose→write pivot
# runs ONE read-once pass + a deterministic write — there are no per-chunk
# budgets. A SINGLE background watchdog (armed once in main() around the whole
# invoke_subprocess) bounds TOTAL run time at start+SDK_MEMORY_TIMEOUT, replacing
# the 036 per-attempt watchdog that re-armed each retry (≈80-min path). macOS-safe
# (no timeout(1) dependency). Timeout -> the watchdog kills the PID tree (TERM
# then KILL); the trap releases the lock; the run reports exit 22 and is NOT
# whole-pipeline-retried.
SDK_MEMORY_TIMEOUT="${SDK_MEMORY_TIMEOUT:-600}"

# Source ~/.claude/.env (mode 0600) so CLAUDE_CODE_OAUTH_TOKEN is available before pre-req checks.
if [ -f "${HOME}/.claude/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "${HOME}/.claude/.env"
    set +a
fi

check_venv_python() {
    if [ ! -x "${VENV_PYTHON}" ]; then
        echo "SDK memory: venv missing; from repo root run: uv venv .claude/.venv --python 3.13 && uv pip install --python .claude/.venv/bin/python claude-agent-sdk"
        exit 14
    fi
}

check_python_version() {
    local version
    version="$("${VENV_PYTHON}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    if ! "${VENV_PYTHON}" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
        echo "SDK memory: .claude/.venv/bin/python is ${version}; need >= 3.10"
        exit 12
    fi
}

check_sdk_importable() {
    if ! "${VENV_PYTHON}" -c 'import claude_agent_sdk' 2>/dev/null; then
        echo "SDK memory: claude-agent-sdk not installed in .claude/.venv; run uv pip install --python .claude/.venv/bin/python claude-agent-sdk"
        exit 11
    fi
}

check_oauth_token() {
    if [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
        echo "SDK memory: CLAUDE_CODE_OAUTH_TOKEN not set; see specs/026-anthropic-api-key-removal/spec.md pre-requisites"
        exit 10
    fi
}

check_jq() {
    if ! command -v jq >/dev/null 2>&1; then
        echo "SDK memory: jq missing; brew install jq"
        exit 13
    fi
}

run_prereq_checks() {
    check_venv_python
    check_python_version
    check_sdk_importable
    check_oauth_token
    check_jq
}

release_lock() {
    if [ -f "${LOCK_FILE}" ]; then
        local owner
        owner="$(cat "${LOCK_FILE}" 2>/dev/null || true)"
        if [ "${owner}" = "$$" ]; then
            rm -f "${LOCK_FILE}"
        fi
    fi
}

acquire_lock() {
    mkdir -p "${LOCK_DIR}"
    if [ -f "${LOCK_FILE}" ]; then
        local existing_pid
        existing_pid="$(cat "${LOCK_FILE}" 2>/dev/null || true)"
        if [ -n "${existing_pid}" ] && kill -0 "${existing_pid}" 2>/dev/null; then
            echo "SDK memory: prior run still active (PID ${existing_pid}); skipping"
            exit 2
        fi
        echo "SDK memory: overriding stale lock (PID ${existing_pid:-unknown} dead)"
        rm -f "${LOCK_FILE}"
    fi
    echo "$$" > "${LOCK_FILE}"
    # SIGTERM/SIGINT/SIGHUP cover a watchdog or operator kill so the lock is released
    # even when the process is signalled (not SIGKILL, which the kernel cannot trap —
    # a SIGKILL-left lock is reclaimed by the next run's stale-PID override above). The
    # EXIT trap is armed once at the top of main() as a combined on_exit handler that
    # records spend THEN releases the lock, so we do not register a separate EXIT trap
    # here (a second `trap ... EXIT` would CLOBBER on_exit). release_lock is idempotent
    # (no-op when this PID does not own the lock), safe to call on every terminal exit.
    trap release_lock TERM INT HUP
}

start_logging() {
    mkdir -p "${LOG_DIR}"
    local ts session_id log_path
    ts="$(date -u +%Y%m%dT%H%M%SZ)"
    session_id="${CLAUDE_SESSION_ID:-$$}"
    log_path="${LOG_DIR}/${ts}-${session_id}.log"
    LOG_PATH="${log_path}"
    exec 2>>"${log_path}"
}

check_session_id() {
    if [ -z "${CLAUDE_SESSION_ID:-}" ]; then
        echo "SDK memory: CLAUDE_SESSION_ID empty; refusing to run with unscoped input"
        exit 25
    fi
}

# Whole-run watchdog state. WATCHDOG_PID is set by arm_watchdog (called ONCE in
# main()) and cleared by disarm_watchdog. The watchdog kills the launcher's own
# process group at start+SDK_MEMORY_TIMEOUT, so it bounds TOTAL run time across
# the read-once pass + the deterministic write + any 20/21 retry sleep.
WATCHDOG_PID=""

arm_watchdog() {
    local target_pid="$1"
    (
        sleep "${SDK_MEMORY_TIMEOUT}"
        if kill -0 "${target_pid}" 2>/dev/null; then
            echo "SDK memory: whole-run budget ${SDK_MEMORY_TIMEOUT}s exceeded; killing run" >&2
            kill -TERM "${target_pid}" 2>/dev/null || true
            sleep 2
            kill -KILL "${target_pid}" 2>/dev/null || true
        fi
    ) &
    WATCHDOG_PID=$!
}

disarm_watchdog() {
    if [ -n "${WATCHDOG_PID}" ] && kill -0 "${WATCHDOG_PID}" 2>/dev/null; then
        kill -TERM "${WATCHDOG_PID}" 2>/dev/null || true
        wait "${WATCHDOG_PID}" 2>/dev/null || true
    fi
    WATCHDOG_PID=""
}

invoke_subprocess() {
    local spec_path="$1"
    local session_id="$2"
    local attempt=1
    local max_attempts=4
    local code=0
    while [ "${attempt}" -le "${max_attempts}" ]; do
        code=0
        "${VENV_PYTHON}" "${ENTRY_SCRIPT}" "${spec_path}" "${session_id}" || code=$?
        # SIGTERM exit = 143, SIGKILL = 137 — the whole-run watchdog killed the
        # process. Map either to the timeout exit 22 (NOT whole-pipeline-retried).
        if [ "${code}" -eq 143 ] || [ "${code}" -eq 137 ]; then
            code=22
        fi
        # Only transient network/rate-limit conditions (20 rate-limit, 21 network)
        # are retried — once each. Every other outcome (success, deterministic
        # failure, OR a timeout-class 22) is terminal here: a re-run would either
        # re-produce the same deterministic result or burn the whole-run budget.
        case "${code}" in
            20|21)
                ;;
            *)
                return "${code}"
                ;;
        esac
        if [ "${attempt}" -ge "${max_attempts}" ]; then
            return "${code}"
        fi
        # Jittered 60-90s clears the per-minute ITPM bucket (research:83).
        sleep $((RANDOM % 30 + 60))
        attempt=$((attempt + 1))
    done
    return "${code}"
}

# --- Spend capture (spec 039 M8) ----------------------------------------------
# The launcher OWNS the canonical per-run marker because it always runs (including
# pre-LLM terminal exits 10-14 that never reach Python's ResultMessage handler).
# Python supplies the cost/token half via the `_last-run-cost.json` sidecar; the
# launcher composes the 7-field `_last-run.json` and merges the cumulative
# `_spend-total.json`. Both live under gitignored ${LOG_DIR}. Smoke points LOG_DIR
# at the tmp tree, so a smoke never writes the real markers.

compose_last_run() {
    # Compose ${LOG_DIR}/_last-run.json from the cost sidecar (if present, else
    # all-null cost/tokens — recorded-as-absent, Rule 2) + launcher-known fields.
    local code="$1"
    local duration="$2"
    local model="$3"
    local sidecar="${LOG_DIR}/_last-run-cost.json"
    local marker="${LOG_DIR}/_last-run.json"
    local ts
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    mkdir -p "${LOG_DIR}"
    if [ -f "${sidecar}" ]; then
        jq -n \
            --argjson code "${code}" \
            --argjson duration "${duration}" \
            --arg model "${model}" \
            --arg ts "${ts}" \
            --slurpfile cost "${sidecar}" \
            '{exit_code: $code, duration_s: $duration,
              cost_usd: $cost[0].cost_usd, tokens_in: $cost[0].tokens_in,
              tokens_out: $cost[0].tokens_out, model: $model, timestamp: $ts}' \
            > "${marker}"
    else
        jq -n \
            --argjson code "${code}" \
            --argjson duration "${duration}" \
            --arg model "${model}" \
            --arg ts "${ts}" \
            '{exit_code: $code, duration_s: $duration,
              cost_usd: null, tokens_in: null, tokens_out: null,
              model: $model, timestamp: $ts}' \
            > "${marker}"
    fi
    # Consume the sidecar so a later null-sidecar run does not reuse a stale cost.
    rm -f "${sidecar}"
}

merge_spend_total() {
    # Read-add-write merge of ${LOG_DIR}/_last-run.json into _spend-total.json:
    # sum cost/tokens (null adds 0), always +1 run_count. Never replaces.
    local marker="${LOG_DIR}/_last-run.json"
    local total="${LOG_DIR}/_spend-total.json"
    [ -f "${marker}" ] || return 0
    mkdir -p "${LOG_DIR}"
    if [ ! -f "${total}" ]; then
        echo '{"cost_usd": 0, "tokens_in": 0, "tokens_out": 0, "run_count": 0}' > "${total}"
    fi
    local merged
    merged="$(jq -s \
        '.[0] as $t | .[1] as $r |
         {cost_usd: (($t.cost_usd // 0) + ($r.cost_usd // 0)),
          tokens_in: (($t.tokens_in // 0) + ($r.tokens_in // 0)),
          tokens_out: (($t.tokens_out // 0) + ($r.tokens_out // 0)),
          run_count: (($t.run_count // 0) + 1)}' \
        "${total}" "${marker}")"
    printf '%s\n' "${merged}" > "${total}"
}

record_spend() {
    # Compose the per-run marker + merge the cumulative total. Called on EVERY
    # terminal exit path (success, deterministic failure, pre-LLM exit). Spend
    # capture is best-effort — a marker failure must not change the run's exit code.
    local code="$1"
    local duration="$2"
    local model="${SDK_MEMORY_MODEL:-opus}"
    compose_last_run "${code}" "${duration}" "${model}" || true
    merge_spend_total || true
}

# Set once at the top of main() so the EXIT trap can record spend even on a
# pre-LLM terminal exit (10-14) that never reaches the explicit record_spend call.
RUN_START_TS=0
SPEND_RECORDED=0

record_spend_on_exit() {
    # Spend recorder: guarantees a marker on EVERY terminal exit, including the
    # prereq-check exits (10-14) that exit before any explicit call. Idempotent via
    # SPEND_RECORDED so a normal run does not double-merge. The exit code is passed in
    # by the caller (on_exit captures $? as its FIRST line); spend capture is
    # best-effort and never alters the run's exit code.
    local code="$1"
    if [ "${SPEND_RECORDED}" = "1" ]; then
        return 0
    fi
    SPEND_RECORDED=1
    local duration=0
    if [ "${RUN_START_TS}" != "0" ]; then
        duration=$(( $(date +%s) - RUN_START_TS ))
    fi
    record_spend "${code}" "${duration}"
}

on_exit() {
    # Single combined EXIT handler. Capturing $? FIRST is load-bearing: any command
    # run before this assignment would overwrite the real exit status. record_spend
    # then runs (best-effort, never changes the code) and release_lock runs last so
    # the lock is freed on every terminal exit including pre-LLM exits 10-14 (armed
    # before run_prereq_checks). Bash EXIT traps REPLACE rather than stack, so this is
    # the ONLY EXIT trap; release_lock is idempotent when this PID owns no lock.
    local code=$?
    record_spend_on_exit "${code}"
    release_lock
}

emit_exit_message() {
    local code="$1"
    local logpath="$2"
    case "${code}" in
        0)
            ;;
        2)
            echo "SDK memory: prior run still active (PID <n>); skipping"
            ;;
        10)
            echo "SDK memory: CLAUDE_CODE_OAUTH_TOKEN not set; see specs/026-anthropic-api-key-removal/spec.md pre-requisites"
            ;;
        11)
            echo "SDK memory: claude-agent-sdk not installed in .claude/.venv; run uv pip install --python .claude/.venv/bin/python claude-agent-sdk"
            ;;
        12)
            echo "SDK memory: .claude/.venv/bin/python is <version>; need >= 3.10"
            ;;
        13)
            echo "SDK memory: jq missing; brew install jq"
            ;;
        14)
            echo "SDK memory: venv missing; from repo root run: uv venv .claude/.venv --python 3.13 && uv pip install --python .claude/.venv/bin/python claude-agent-sdk"
            ;;
        20)
            echo "SDK memory: rate-limited; memory not updated this deliver"
            ;;
        21)
            echo "SDK memory: network failure; memory not updated this deliver"
            ;;
        22)
            echo "SDK memory: subprocess hit the whole-run safety-net timeout (${SDK_MEMORY_TIMEOUT}s); killed"
            ;;
        23)
            echo "SDK memory: mirror write failed; cross-checker will flag at next verify"
            ;;
        24)
            echo "SDK memory: agent hit max_turns ceiling; not retried (raise SDK_MEMORY_MAX_TURNS if needed)"
            ;;
        25)
            echo "SDK memory: CLAUDE_SESSION_ID empty; refusing to run with unscoped input"
            ;;
        26)
            echo "SDK memory: topic-slug recurrence (cross-spec drift); see ${logpath} (run NOT retried)"
            ;;
        27)
            echo "SDK memory: orphan/dead-link check failed; see ${logpath} (memory index inconsistent)"
            ;;
        30)
            echo "SDK memory: silo-shape / nested-path violation; see ${logpath} (run NOT retried)"
            ;;
        31)
            echo "SDK memory: proposal schema-validation failed; nothing written; see ${logpath} (run NOT retried)"
            ;;
        33)
            echo "SDK memory: post-run repo-side silo-leak detected; see ${logpath} (silos are canonical-only; run NOT retried)"
            ;;
        34)
            echo "SDK memory smoke: all-store assertion failed — the proposal omitted a silo entry or a shared_topic; see ${logpath} (smoke-only; run NOT retried)"
            ;;
        *)
            echo "SDK memory: subprocess exited ${code}; see ${logpath}"
            ;;
    esac
}

run_smoke() {
    # Pre-deliver real-run smoke gate (spec 038 M8, AC-12). Runs the REAL launcher
    # + live LLM against the committed scratch corpus, writing into a TMP canonical
    # dir + TMP repo root — NEVER the real ~/.claude/projects store or the real
    # repo. The orchestrator runs this at verify→deliver BEFORE the commit; a
    # non-zero exit blocks the gate. The post-run repo-side-silo-leak (exit 33) and
    # nested-.claude (exit 30) assertions in the Python entry run against the TMP
    # repo root, so a leak FAILS the smoke run.
    run_prereq_checks

    local corpus="${REPO_ROOT}/.claude/hooks/tests/fixtures/smoke-corpus"
    if [ ! -d "${corpus}" ]; then
        echo "SDK memory smoke: corpus missing at ${corpus}"
        return 1
    fi

    local smoke_root tmp_canonical tmp_repo
    smoke_root="$(mktemp -d "${TMPDIR:-/tmp}/sdk-memory-smoke.XXXXXX")"
    tmp_canonical="${smoke_root}/canonical"
    tmp_repo="${smoke_root}/repo"
    mkdir -p "${tmp_canonical}" "${tmp_repo}/.claude"

    # Seed the tmp canonical store + a copy of the scratch spec into the tmp repo.
    cp -R "${corpus}/canonical/." "${tmp_canonical}/"
    cp -R "${corpus}/specs" "${tmp_repo}/.claude/specs"

    local smoke_spec="${tmp_repo}/.claude/specs/900-smoke"

    # SYNTHETIC session (spec 038 M8 fix): the smoke must NOT read the real live
    # session — that transcript is about whatever real spec is in flight, so the
    # LLM would propose THAT spec's topics and the recurrence guard (exit 26) would
    # reject the cross-spec drift vs the delivered 900-smoke. The corpus commits a
    # tiny fake transcript grounded in 900-smoke; we point the session at it (and
    # never pass the real CLAUDE_SESSION_ID into the subprocess).
    local smoke_session="smoke-900-session"
    if [ -f "${corpus}/session/${smoke_session}.jsonl" ]; then
        cp "${corpus}/session/${smoke_session}.jsonl" "${tmp_canonical}/${smoke_session}.jsonl"
    fi

    # Overrides the Python `_run` reads for the smoke path: canonical store, repo
    # root, AND session all point into the tmp/synthetic tree. The real store and
    # the real session are never touched.
    export SDK_MEMORY_CANONICAL_OVERRIDE="${tmp_canonical}"
    export SDK_MEMORY_REPO_OVERRIDE="${tmp_repo}"
    export SDK_MEMORY_SESSION_OVERRIDE="${smoke_session}"
    # Smoke signal: gates OUT the cross-spec recurrence guard (exit 26) ONLY — a
    # real-deliver-only check a synthetic-spec run in the real repo cannot satisfy.
    # Every other post-write check (leak/nested/orphan/shape) stays active.
    export SDK_MEMORY_SMOKE=1

    echo "SDK memory smoke: corpus=${corpus} tmp=${smoke_root} session=${smoke_session}" >&2
    cd "${REPO_ROOT}"

    local code=0
    arm_watchdog "$$"
    "${VENV_PYTHON}" "${ENTRY_SCRIPT}" "${smoke_spec}" "${smoke_session}" || code=$?
    disarm_watchdog

    if [ "${code}" -eq 143 ] || [ "${code}" -eq 137 ]; then
        code=22
    fi
    emit_exit_message "${code}" "${smoke_root}"
    if [ "${code}" -eq 0 ]; then
        echo "SDK memory smoke: PASS (tmp tree ${smoke_root})"
    else
        echo "SDK memory smoke: FAIL exit ${code} (tmp tree ${smoke_root})"
    fi
    return "${code}"
}

main() {
    if [ "${1:-}" = "--check" ]; then
        run_prereq_checks
        exit 0
    fi

    if [ "${1:-}" = "--smoke" ]; then
        local smoke_code=0
        run_smoke || smoke_code=$?
        exit "${smoke_code}"
    fi

    # Arm the combined EXIT handler BEFORE run_prereq_checks so the per-run spend
    # marker is written even on a pre-LLM terminal exit (10-14). RUN_START_TS is set
    # to the real clock here so duration_s reflects actual wall time. This is the
    # only EXIT trap (acquire_lock no longer registers a separate one); on_exit
    # records spend THEN releases the lock. Set after the --check/--smoke branches so
    # those modes never write the real spend markers.
    RUN_START_TS=$(date +%s)
    trap on_exit EXIT

    check_session_id
    run_prereq_checks
    acquire_lock
    start_logging

    # Run the SDK subprocess from the repo ROOT (spec 036 M5, AC-9). The Python
    # entry derives `project_slug` from cwd and the SDK uses cwd as its working
    # dir; running from `.claude/hooks/` (the hook's default cwd) both broke the
    # slug and scaffolded nested `.claude/.claude/` / `.claude/hooks/.claude/`
    # dirs (035). All paths above are already absolute, so the cd is safe.
    cd "${REPO_ROOT}"

    local spec_path="${1:-${SPEC_PATH:-}}"
    if [ -z "${spec_path}" ]; then
        echo "SDK memory: subprocess exited 1; see ${LOG_PATH}"
        exit 1
    fi

    # Arm ONE whole-run watchdog around the entire invoke_subprocess (read-once
    # pass + deterministic write + any 20/21 retry sleep) — bounds TOTAL run time
    # at start+SDK_MEMORY_TIMEOUT. Disarmed as soon as the run returns so a fast
    # run does not wait out the budget.
    arm_watchdog "$$"

    local final_code=0
    invoke_subprocess "${spec_path}" "${CLAUDE_SESSION_ID}" || final_code=$?

    disarm_watchdog

    emit_exit_message "${final_code}" "${LOG_PATH}"
    exit "${final_code}"
}

main "$@"

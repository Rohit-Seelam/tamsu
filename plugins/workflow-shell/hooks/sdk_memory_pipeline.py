"""SDK memory pipeline subprocess entry point.

Propose→write architecture (spec 038)
--------------------------------------
The pipeline is split into two halves so that file writes are deterministic and
leak-proof, not LLM-driven:

  (a) LLM half — ONE bounded read-once pass. `_run` issues a SINGLE SDK `query()`
      whose `allowed_tools` are Read/Glob/Grep ONLY (no Write/Edit). The agent
      reads the spec + session + existing memory once and EMITS a single
      structured PROPOSAL object (which decisions / project-topics / per-silo /
      shared-topics entries to record). It writes ZERO files — structurally, the
      LLM half has no write tool.

  (b) Deterministic writer — `_memory_writer.write_proposal` consumes that
      proposal and OWNS every written path, the `MEMORY.md` index-line shape, the
      per-store TRUNCATING CAP (writes the first N per store, drops + logs the
      excess), the canonical-vs-repo split, and personal-line filtering. Same
      proposal in → byte-identical files out. This in-process Python writer is NOT
      a Write/Edit tool call, so the SDK-actor process remains the sole memory
      writer (Rule 5).

The proposal is schema-validated by the pure `_proposal_schema.validate_proposal`
(exit 31 on violation) before the writer sees it; the writer TRUNCATES an
over-budget set to the per-store caps (writing top-N, dropping + logging the
excess — a normal exit-0 write); a post-run scan fails the run on any repo-side
silo leak (exit 33). This replaces the superseded "LLM writes everything across
many bounded loops, then mechanically check" flow. Full contract:
`.claude/workflow/sdk-pipeline.md`.
"""

import asyncio
import fnmatch
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLAUDE_ROOT = REPO_ROOT / ".claude"

# Dedicated post-write exit: the writer reported a silo path that is ABSENT from
# the auto-load location (spec 047 AC-2). A run-failure (terminal) so the silent
# silo no-op can never recur unnoticed — exit-0 + a `wrote N file(s)` count is NOT
# a landing signal.
EXIT_SILO_ABSENT = 35

_LEARNING_RE = re.compile(r"^\s*\[learning\]\s*(.+?)\s*$", re.MULTILINE)
_LEARNING_CAP_LINES = 200
_LEARNING_CAP_BYTES = 25 * 1024

# The fixed set of subagents carrying `memory: project` (spec 034). The pipeline
# writes one silo index per agent at every `deliver`; the set is closed, so the
# subprocess is told the names rather than discovering them. SINGLE-SOURCED from
# `_budget_check` (Rule 7) — `frontend-engineer` left the roster as dormant in
# spec 047 AC-6c, so this re-export keeps the prompt/orphan-check in lockstep.
from _budget_check import SILO_AGENTS

_SILO_CAP_LINES = 200
_SILO_CAP_BYTES = 25 * 1024

# Personal / canonical-only class (spec 035 M5, AC-12). Single-sourced from
# `workflow/artifacts.md` "Selective mirror policy" (artifacts.md:227-232): the
# user's role, communication style, and personal feedback/preferences live ONLY
# in the canonical store and are NEVER mirrored into the shareable repo template.
# `_mirror_canonical_to_repo` excludes any basename matching one of these globs.
_PERSONAL_EXCLUDE = (
    "user_role.md",
    "user_communication.md",
    "feedback_*.md",
    "preferences.md",
)


def _is_personal(name: str) -> bool:
    """True if a memory-store basename belongs to the personal/canonical-only class."""
    return any(fnmatch.fnmatch(name, pattern) for pattern in _PERSONAL_EXCLUDE)


# Match the LINK target of a Markdown index line: `](<target>)`. The mirror
# strips a line whose link BASENAME is personal — keyed on the link, not the
# title text (a non-personal title can point at a personal file).
_INDEX_LINK_RE = re.compile(r"\]\(([^()\s]+)\)")


def _strip_personal_index_lines(memory_md_text: str) -> str:
    """Drop any `MEMORY.md` index line whose link basename is in the personal
    class (spec 038 M5, AC-8). Closes the 036 gap where personal FILES were
    excluded but their index LINES were mirrored through, leaving dead links in
    the repo `MEMORY.md`. A line with no link, or a non-personal link, is kept."""
    kept: list[str] = []
    for line in memory_md_text.splitlines():
        links = _INDEX_LINK_RE.findall(line)
        if any(_is_personal(Path(link).name) for link in links):
            continue
        kept.append(line)
    trailing_newline = "\n" if memory_md_text.endswith("\n") else ""
    return "\n".join(kept) + trailing_newline


def _mirror_canonical_to_repo(
    *,
    canonical_memory_dir: str | os.PathLike[str],
    repo_memory_dir: str | os.PathLike[str],
) -> list[str]:
    """Mechanically mirror the NON-personal subset of canonical `memory/` into the
    repo mirror (the canonical-authored + mechanical-mirror model; contract in
    workflow/sdk-pipeline.md).

    Deterministic in-process Python `shutil` copy — NOT a Write/Edit/MultiEdit
    tool call, so `memory-write-guard.sh` does not intercept it and the SDK-actor
    process is legitimately the sole writer (Rule 5). The source is locked to the
    outer `memory/` store by ROOT name, AND any source path whose `.parts` contain
    `agent-memory` is skipped per-path — so no `agent-memory` descendant (nested or
    otherwise) is EVER copied to the repo, regardless of how it arrived in the
    canonical tree (spec 039 M1: a STALE nested `memory/agent-memory/` tree was the
    038 real-run leak vector). Silos + shared topics are canonical-only.

    The personal/canonical-only class (`_PERSONAL_EXCLUDE`) is skipped at both the
    top level and inside `topics/`. Returns the sorted list of repo-relative paths
    written.
    """
    src = Path(canonical_memory_dir) / "memory"
    dst = Path(repo_memory_dir)
    # Mechanical lock (spec 036 M3, AC-7): the mirror copies the outer `memory/`
    # store ONLY. Silos (`agent-memory/`) are canonical-only and must never be
    # mirrored — 035 leaked 57 silo files. A regression that repointed the source
    # at the silo store fails loudly here (surfaced, not swallowed: Rule 2).
    if src.name != "memory":
        raise ValueError(
            f"_mirror_canonical_to_repo source must be the outer memory/ store, "
            f"got {src.name!r}; silos are canonical-only and never mirrored"
        )
    written: list[str] = []
    if not src.is_dir():
        return written
    dst.mkdir(parents=True, exist_ok=True)
    for source in sorted(src.rglob("*.md")):
        rel = source.relative_to(src)
        # Per-path skip (spec 039 M1): any agent-memory descendant is canonical-only
        # and never mirrored. Match a path PART equal to "agent-memory" (not a
        # substring), so a legitimately named outer topic is not over-skipped.
        if "agent-memory" in rel.parts:
            continue
        if _is_personal(source.name):
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.name == "MEMORY.md":
            # Filter personal index LINES (not just files) so the repo MEMORY.md
            # carries no dead link to an excluded personal file (spec 038 M5).
            filtered = _strip_personal_index_lines(
                source.read_text(encoding="utf-8")
            )
            target.write_text(filtered, encoding="utf-8")
        else:
            shutil.copy2(source, target)
        written.append(str(rel))
    return written

def _build_workflow_files() -> list[Path]:
    """Resolve the stable cacheable-prefix file bundle.

    Per AC-10 (`specs/020-sdk-session-targeting/spec.md`):
      - every `workflow/*.md` file (README, phases, artifacts, routing,
        communication, evaluation)
      - `constitution.md`
      - every `agents/**/*.md`
      - `skills/memory/jsonl-format/SKILL.md`
      - `skills/memory/extraction-learnings/SKILL.md`

    Every entry must exist at import time; a missing file raises
    `FileNotFoundError` at first prompt build (`_workflow_system_prompt`),
    blocking the SDK loop before it consumes API budget.
    """
    files: list[Path] = []
    for fname in (
        "README.md",
        "phases.md",
        "artifacts.md",
        "routing.md",
        "communication.md",
        "evaluation.md",
    ):
        files.append(CLAUDE_ROOT / "workflow" / fname)
    files.append(CLAUDE_ROOT / "constitution.md")
    files.extend(sorted((CLAUDE_ROOT / "agents").rglob("*.md")))
    files.append(CLAUDE_ROOT / "skills" / "memory" / "jsonl-format" / "SKILL.md")
    files.append(CLAUDE_ROOT / "skills" / "memory" / "extraction-learnings" / "SKILL.md")
    return files


WORKFLOW_FILES = _build_workflow_files()


def _read_file(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"required prompt input missing: {path}")
    return path.read_text(encoding="utf-8")


def _read_spec_folder(spec_path: Path) -> str:
    if not spec_path.is_dir():
        raise FileNotFoundError(f"spec folder missing: {spec_path}")
    parts: list[str] = []
    for entry in sorted(spec_path.rglob("*.md")):
        if entry.is_file():
            rel = entry.relative_to(spec_path)
            parts.append(f"### {rel}\n\n{entry.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def _workflow_system_prompt() -> str:
    # Stable workflow-doc bundle for the cacheable system-prompt prefix (research:65, plan M2).
    sections: list[str] = []
    for source in WORKFLOW_FILES:
        rel = source.relative_to(REPO_ROOT)
        sections.append(f"## {rel}\n\n{_read_file(source)}")
    return "\n\n".join(sections)


_PREAMBLE = (
    "You are the SDK memory pipeline subprocess. "
    "Your job is to READ the just-completed spec ONCE and EMIT a single "
    "structured PROPOSAL of memory entries — NOT to write files and NOT to chat "
    "with the user. A deterministic Python writer turns your proposal into files; "
    "you have no Write/Edit tool."
)

# The proposal schema the LLM half must emit (single source rendered into the
# prompt). The deterministic `_memory_writer` consumes exactly this object and
# the pure `_proposal_schema.validate_proposal` gates it (exit 31).
_PROPOSAL_SCHEMA_BLOCK = (
    "Emit your result as a single fenced JSON object with EXACTLY these keys:\n\n"
    "```json\n"
    "{\n"
    '  "decisions": [{"title": "...", "hook": "...", "body": "..."}],\n'
    '  "project_topics": [{"slug": "...", "title": "...", "hook": "...", '
    '"body": "...", "append": false}],\n'
    '  "silos": {"<agent>": [{"title": "...", "topic_slug": "...", "hook": "..."}]},\n'
    '  "shared_topics": [{"slug": "...", "title": "...", "hook": "...", "body": "..."}]\n'
    "}\n"
    "```\n\n"
    f"`silos` keys MUST be one of: {', '.join(SILO_AGENTS)}. Each silo entry's "
    "`topic_slug` MUST be a BARE slug (no '/') referencing a ROOT shared topic at "
    f"{CLAUDE_ROOT.relative_to(REPO_ROOT)}/agent-memory/topics/<slug>.md — never a "
    "nested <agent>/topics/ path. `project_topics[].slug` and `shared_topics[].slug` "
    "are bare slugs too. Set `append: true` on a project topic when the note belongs "
    "to an existing topic surface (depth rule: append over create).\n\n"
    "NAMESPACE RULE (two DISTINCT slug pools — do not conflate them): a silo entry's "
    f"`topic_slug` MUST resolve to an existing {CLAUDE_ROOT.relative_to(REPO_ROOT)}/"
    "agent-memory/topics/<slug>.md slug OR to a `shared_topics[]` slug you emit in "
    "THIS SAME proposal. It MUST NEVER be an OUTER memory/topics/*.md slug — the outer "
    f"{CLAUDE_ROOT.relative_to(REPO_ROOT)}/memory/topics/ namespace (the mirrored, "
    "auto-loaded project-memory pool) is a SEPARATE, FORBIDDEN pool for a silo "
    "`topic_slug`. If a silo's craft references cross-agent knowledge that only exists "
    "as an outer memory topic, create a NEW `shared_topics[]` entry for it in this "
    "proposal and point the silo `topic_slug` at that new shared slug — never at the "
    "outer slug directly. The silo-resolvable slug-set is enumerated in the prompt "
    "context below."
)


def _proposal_directive() -> str:
    return (
        "You are the SDK memory pipeline subprocess. Read the just-completed spec, "
        "its session transcript, and the existing memory stores ONCE (Read/Glob/Grep "
        "only — you have no Write/Edit tool), then EMIT a single structured proposal "
        "of the durable memory entries to record, per the contract in "
        ".claude/workflow/sdk-pipeline.md.\n\n"
        "Cover: project decisions (decisions.md), project spec-topics, the per-agent "
        f"silos for these {len(SILO_AGENTS)} agents ({', '.join(SILO_AGENTS)}), and shared cross-agent "
        "topics. Derive each agent's reusable craft from its per-actor transcript "
        "(use the actor map below, which names which agent-<id> performed each phase) "
        "— capture reusable craft, not task state. Cross-agent lessons (relevant to "
        "more than one agent) belong in `shared_topics`, referenced from each relevant "
        "silo entry's `topic_slug`, never duplicated. Before proposing a new topic, "
        "search existing topics by slug AND by subject substring so you reference an "
        "existing surface (append) rather than creating a duplicate variant.\n\n"
        "MEMORY-vs-QUEUE BOUNDARY (spec 047 AC-6b): `memory/` holds LANDED decisions "
        "and characterization findings — what was decided and why, what is true now. "
        "PENDING work belongs in `workflow/queue.md`, NOT here. Do NOT propose an outer "
        "`decisions` or `project_topics` entry framed as deferred work — anything reading "
        "as 'followup', 'TODO', 'bundle with the next touch', 'defer', or 'in a later "
        "spec'. If the spec left a loose end, that is a queue item, not a memory entry. "
        "(A silo craft note may legitimately name a followup in its own craft hook.)\n\n"
        "SPEC-ID BINDING RULE (spec 055): a NEW spec-bound `project_topics` entry MUST "
        "be named `spec-<NNN>-...` using THIS deliver's spec id — the number shown in "
        "the `## spec folder:` header below. It MUST NEVER be filed under a DIFFERENT "
        "spec's EXISTING slug (e.g. do NOT reuse `spec-024-...` on a spec-055 deliver) — "
        "doing so OVERWRITES that prior spec's topic file. To intentionally append a "
        "closure note to a prior spec's surface, reference that slug AND set "
        "`append: true` on the entry (the sanctioned closure-note path); a bare "
        "cross-spec slug is rejected before any write.\n\n"
        + _budget_block()
        + "\n\n"
        + _PROPOSAL_SCHEMA_BLOCK
    )


def _budget_block() -> str:
    """The per-store write BUDGET numbers, single-sourced from `_budget_check` so
    the prompt and the deterministic writer agree (spec 038, truncate decision).

    The writer enforces these as TRUNCATING ceilings (writes the first N per store,
    drops + logs the excess). Propose WITHIN budget, MOST-IMPORTANT-FIRST per store,
    so the only entries ever dropped are the least-important tail."""
    from _budget_check import (
        DECISIONS_LIMIT,
        SHARED_TOPICS_LIMIT,
        SILO_LIMIT,
        SPEC_TOPICS_LIMIT,
    )

    return (
        "Per-deliver write BUDGET (hard ceilings — the writer TRUNCATES to these and "
        "drops the excess, so propose WITHIN budget and order each store "
        "MOST-IMPORTANT-FIRST):\n"
        f"- decisions: at most {DECISIONS_LIMIT} entr(y/ies);\n"
        f"- project_topics: at most {SPEC_TOPICS_LIMIT};\n"
        f"- shared_topics: at most {SHARED_TOPICS_LIMIT};\n"
        f"- each WORKED-agent silo: at most {SILO_LIMIT} craft-note (a silo for an "
        "agent that did NOT work this spec gets 0 — do not propose one).\n"
        "Propose the single most durable, reusable entry per store; anything beyond "
        "the budget will be silently dropped from the tail, so do NOT rely on it landing."
    )


def _rel_to_repo(path: Path, repo_root: Path) -> str:
    """Render `path` relative to `repo_root`, robust to a spec_dir living OUTSIDE
    the root (the --smoke tmp repo, spec 038 M8): falls back to the path basename
    rather than raising. Without this, a smoke spec under a tmp repo broke prompt
    assembly via `relative_to(REPO_ROOT)` before the live pass even started."""
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return path.name


def _silo_resolvable_slugs(
    canonical_dir: str | os.PathLike[str],
) -> list[str]:
    """The existing canonical `agent-memory/topics/` slug stems (the silo-resolvable
    pool), sorted. Same on-disk source the validator caller uses
    (`_proposal_schema_validate`) — no new disk-walk shape. The base lives UNDER
    the auto-memory root `memory/` (spec 047 AC-1)."""
    from _memory_writer import agent_memory_base

    shared_topics_dir = agent_memory_base(canonical_dir) / "topics"
    if not shared_topics_dir.is_dir():
        return []
    return sorted(p.stem for p in shared_topics_dir.glob("*.md"))


def _render_silo_slug_set_section(canonical_dir: str | os.PathLike[str]) -> str:
    """A positive, enumerated signal of which slugs a silo `topic_slug` MAY
    reference (spec 042 AC-2). The OUTER `memory/topics/` pool is intentionally NOT
    listed here — naming it would re-introduce the conflation this guard prevents;
    the NAMESPACE RULE in the schema block names it only as the FORBIDDEN pool."""
    slugs = _silo_resolvable_slugs(canonical_dir)
    body = (
        "\n".join(f"- {s}" for s in slugs)
        if slugs
        else "(none yet — propose a `shared_topics[]` entry and cite it)"
    )
    return (
        "## silo-resolvable slug-set (agent-memory/topics/)\n\n"
        "A silo entry's `topic_slug` MUST be one of these existing "
        "`agent-memory/topics/` slugs OR a `shared_topics[]` slug you emit in this "
        "proposal — NEVER an outer `memory/topics/` slug:\n\n"
        f"{body}"
    )


def _build_base_sections(
    spec_dir: Path,
    session_id: str | None,
    canonical_dir: str | os.PathLike[str] | None,
    *,
    repo_root: Path | None = None,
) -> list[str]:
    """Spec-folder + scope/actor/ledger sections for the proposal prompt.

    `repo_root` is the EFFECTIVE repo root used to render the spec-folder header
    relative path; it defaults to the module-level `REPO_ROOT` but the --smoke
    path passes its tmp repo root so the header resolves against that tree."""
    effective_root = repo_root if repo_root is not None else REPO_ROOT
    sections: list[str] = [
        f"## spec folder: {_rel_to_repo(spec_dir, effective_root)}\n\n{_read_spec_folder(spec_dir)}"
    ]
    if canonical_dir is not None:
        sections.append(_render_silo_slug_set_section(canonical_dir))
    if session_id and canonical_dir is not None:
        from _session_scope import build_scope, render_scope_section
        from _actor_map import build_actor_map, render_actor_map_section
        from _phase_ledger import build_phase_ledger, render_phase_ledger_section

        team_config_path = _resolve_team_config_path(spec_dir)
        scope = build_scope(
            canonical_dir=canonical_dir,
            orchestrator_session_id=session_id,
            team_config_path=team_config_path,
        )
        sections.append(render_scope_section(scope))
        actor_map = build_actor_map(
            canonical_dir=canonical_dir,
            orchestrator_session_id=session_id,
            team_config_path=team_config_path,
        )
        sections.append(render_actor_map_section(actor_map))
        state_path = spec_dir / "state.json"
        if state_path.is_file():
            ledger = build_phase_ledger(state_path, actor_map)
            sections.append(render_phase_ledger_section(ledger))
    return sections


def build_proposal_prompt(
    spec_path: str | os.PathLike[str],
    session_id: str | None = None,
    *,
    canonical_dir: str | os.PathLike[str] | None = None,
    repo_root: str | os.PathLike[str] | None = None,
) -> str:
    """Build the SINGLE read-once proposal prompt (spec 038 M2).

    One prompt, one read-once pass. `## Task` is the first `##`-level section so
    the agent treats it as authoritative; the spec/scope/actor/ledger base
    sections follow. The directive instructs the agent to READ once and EMIT the
    structured proposal JSON; it has no Write/Edit tool.

    `repo_root` is the EFFECTIVE repo root for rendering the spec-folder header
    relative path. It defaults to the module-level `REPO_ROOT`; the --smoke path
    passes its tmp repo root so a spec living under the tmp tree (outside the real
    repo) does not break prompt assembly (spec 038 M8)."""
    spec_dir = Path(spec_path).resolve()
    effective_root = Path(repo_root).resolve() if repo_root is not None else REPO_ROOT
    instructions = "## Task\n\n" + _proposal_directive()
    sections: list[str] = [_PREAMBLE, instructions]
    sections.extend(
        _build_base_sections(spec_dir, session_id, canonical_dir, repo_root=effective_root)
    )
    return "\n\n".join(sections)


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def parse_proposal(result_text: str) -> dict | None:
    """Extract the structured proposal object from the LLM result text.

    Prefers a ```json fenced block; falls back to the first balanced top-level
    `{...}` object. Returns the parsed dict, or None when no JSON object is
    found / it does not parse (the caller maps a None to a schema finding so the
    failure surfaces, never swallowed: Rule 2)."""
    if not result_text:
        return None
    for candidate in _JSON_FENCE_RE.findall(result_text):
        try:
            obj = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    # Fallback: scan for the first balanced brace-object.
    start = result_text.find("{")
    while start != -1:
        depth = 0
        for end in range(start, len(result_text)):
            ch = result_text[end]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(result_text[start : end + 1])
                    except ValueError:
                        break
                    if isinstance(obj, dict):
                        return obj
                    break
        start = result_text.find("{", start + 1)
    return None


def _append_learning(result_text: str, skill_path: str | os.PathLike[str]) -> int:
    """Parse `[learning] <one-line>` markers and append them to the skill file.

    - Returns the count of bullets appended.
    - No append when no markers found.
    - When the resulting file would exceed 200 lines OR 25 KB, the overflow
      lines roll to `extraction-learnings-archive.md` in the same directory
      (AC-13).
    """
    path = Path(skill_path)
    matches = _LEARNING_RE.findall(result_text or "")
    if not matches:
        return 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_bullets = [f"- {today} — {m.strip()}" for m in matches]
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    combined = existing.rstrip("\n") + "\n" + "\n".join(new_bullets) + "\n"
    combined_lines = combined.split("\n")
    combined_bytes = combined.encode("utf-8")
    if len(combined_lines) <= _LEARNING_CAP_LINES and len(combined_bytes) <= _LEARNING_CAP_BYTES:
        path.write_text(combined, encoding="utf-8")
        return len(new_bullets)
    # Overflow: trim newest tail lines into the archive until both caps satisfied.
    archive = path.parent / "extraction-learnings-archive.md"
    archive_existing = archive.read_text(encoding="utf-8") if archive.is_file() else ""
    overflow: list[str] = []
    while (
        len(combined_lines) > _LEARNING_CAP_LINES
        or len("\n".join(combined_lines).encode("utf-8")) > _LEARNING_CAP_BYTES
    ):
        if not combined_lines:
            break
        # Pop from the tail; the file's earliest content (frontmatter, seed
        # heuristics) stays put. The newest bullets are the ones we just
        # appended, so they're the most appropriate to roll into the archive.
        overflow.insert(0, combined_lines.pop())
    path.write_text("\n".join(combined_lines).rstrip("\n") + "\n", encoding="utf-8")
    archive.write_text(
        archive_existing.rstrip("\n") + ("\n" if archive_existing else "") + "\n".join(overflow) + "\n",
        encoding="utf-8",
    )
    return len(new_bullets)


def build_silo_index(agent: str, entries) -> str:
    """Shape + validate a per-agent silo `agent-memory/<agent>/MEMORY.md` index.

    Pure function (no file I/O). Given `(title, topic_slug, hook)` craft entries,
    returns a cap-respecting index in the canonical `- [Title](topics/file.md) — hook`
    shape. Each entry's `topic_slug` references a SHARED ROOT-level topic at
    `agent-memory/topics/<slug>.md` (rendered relative to the silo as
    `topics/<slug>.md`), never a per-agent nested topic.

    Raises `ValueError` for any `topic_slug` that carries a path separator or is
    nested under `<agent>/topics/` — per-agent folders hold only `MEMORY.md`;
    all topic bodies live at the ROOT `agent-memory/topics/` (spec 034 AC-7).

    Caps: the returned text respects BOTH the 200-line and 25KB index caps; the
    newest overflow entries are dropped from the rendered index (the shared topic
    bodies they reference are unaffected), mirroring the `_append_learning` cap
    discipline.
    """
    header = f"# {agent} memory"
    lines: list[str] = []
    for title, topic_slug, hook in entries:
        slug = topic_slug[:-3] if topic_slug.endswith(".md") else topic_slug
        if "/" in slug:
            raise ValueError(
                f"silo topic slug must reference a ROOT agent-memory/topics/<slug>.md "
                f"target, never a nested <agent>/topics/ path: {topic_slug!r}"
            )
        lines.append(f"- [{title}](topics/{slug}.md) — {hook}")

    def _render(body: list[str]) -> str:
        return "\n".join([header, "", *body]) + "\n" if body else header + "\n"

    rendered = _render(lines)
    while lines and (
        len(rendered.splitlines()) > _SILO_CAP_LINES
        or len(rendered.encode("utf-8")) > _SILO_CAP_BYTES
    ):
        lines.pop()
        rendered = _render(lines)
    return rendered


def _resolve_team_config_path(spec_dir: Path) -> Path | None:
    """Return the audit-copy team config for the spec, or None when no team ran.

    Audit copy lives at `specs/<NNN>/teams/<team-name>/config.json`. There is
    one team per spec for the current contract iteration (per spec.md "Out of
    scope: multi-team-per-spec support").
    """
    teams_dir = spec_dir / "teams"
    if not teams_dir.is_dir():
        return None
    for team in sorted(teams_dir.iterdir()):
        candidate = team / "config.json"
        if candidate.is_file():
            return candidate
    return None


# --- Topic-slug recurrence guard (spec 028 AC-5) -------------------------------
#
# The pipeline is an LLM-driven writer with no constraint binding emitted topic
# slugs to the spec being delivered. Across re-runs it produced multiple
# differently-slugged variants for one spec, leaving unindexed orphans. This
# guard rejects cross-spec slug drift: a topic file shaped `spec-<NNN>-...` must
# bind to the just-delivered spec's number. Multiple `spec-<NNN>-*` files for
# the same <NNN> are sanctioned splits and pass. Non-spec-prefixed slugs are
# cross-cutting topics and are never bound to a single spec.

_SPEC_SLUG_RE = re.compile(r"^spec-(\d+)-")
_SPEC_ID_RE = re.compile(r"^(\d+)-")


class MemoryMirrorGuardError(RuntimeError):
    """Raised/surfaced when a written topic-file slug drifts to a spec other
    than the just-delivered one (spec 028 AC-5, constitution Rule 2)."""


def _spec_number(identifier: str) -> str | None:
    """Return the leading spec number embedded in an archived-spec id
    (`028-foo` -> `028`) or a topic-file slug (`spec-028-foo` -> `028`).

    Returns None for cross-cutting identifiers (`decisions`,
    `teams-protocol-resolution`) that are not bound to a single spec.
    """
    stem = identifier[:-3] if identifier.endswith(".md") else identifier
    match = _SPEC_SLUG_RE.match(stem) or _SPEC_ID_RE.match(stem)
    return match.group(1) if match else None


def validate_topic_slugs(
    topic_slugs,
    delivered_spec_id: str,
    *,
    allowlist=None,
) -> list[str]:
    """Return the sorted slug stems that drift to a spec other than the
    just-delivered one.

    A topic slug shaped `spec-<NNN>-...` is bound to spec number <NNN>. It is in
    policy iff <NNN> equals the delivered spec's number, or the slug stem is in
    `allowlist` (a sanctioned cross-spec reference). Non-spec-prefixed slugs are
    cross-cutting topics and are never flagged. Multiple `spec-<NNN>-*` slugs
    sharing the delivered number are all valid (sanctioned multi-topic split).
    """
    allow = set(allowlist or ())
    delivered = _spec_number(delivered_spec_id)
    violations: list[str] = []
    for slug in topic_slugs:
        stem = slug[:-3] if slug.endswith(".md") else slug
        if stem in allow:
            continue
        number = _spec_number(stem)
        if number is None:
            continue  # cross-cutting topic, not bound to a single spec
        if delivered is None or number != delivered:
            violations.append(stem)
    return sorted(violations)


def resolve_delivered_spec_id(
    spec_path: str | os.PathLike[str],
    active_json_path: str | os.PathLike[str],
) -> str:
    """Resolve the just-delivered spec id, binding to `active.json.archived[]`
    as the single source of truth (constitution Rule 7).

    Matches the spec_path's number against archived[] ids and returns the
    archived id. Falls back to the spec_path basename when active.json has no
    archived entry for that number (e.g. guard running before the archive write)
    or cannot be read.
    """
    basename = Path(spec_path).name
    number = _spec_number(basename)
    try:
        data = json.loads(Path(active_json_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return basename
    for entry in data.get("archived", []):
        entry_id = str(entry.get("id", ""))
        if number is not None and _spec_number(entry_id) == number:
            return entry_id
    return basename


def _topic_dirs(canonical_memory_dir: str | os.PathLike[str]) -> list[Path]:
    """The topic store the recurrence guard diffs: the CANONICAL topics dir ONLY.

    The repo mirror (`CLAUDE_ROOT/memory/topics`) is DELIBERATELY excluded. The
    deterministic writer writes canonical topic bodies SURGICALLY — only the slugs
    named in this deliver's proposal get fresh mtimes — so a canonical before/after
    diff is an exact, sufficient signal of "what this deliver wrote". The repo
    mirror, by contrast, is a DERIVED wholesale copy: `_mirror_canonical_to_repo`
    re-copies EVERY canonical topic to the repo each run, so every repo topic file
    gets a fresh mtime regardless of whether the deliver touched it. Including the
    mirror made `changed_topic_slugs` flag the entire accumulated index, so the
    guard rejected every pre-existing `spec-NNN` slug as cross-spec drift (real
    spec-038 deliver: exit 26 on all 23 historical topics). Guarding canonical
    writes alone is the correct + sufficient recurrence signal (spec 038 realrun)."""
    return [
        Path(canonical_memory_dir) / "memory" / "topics",
    ]


def snapshot_topics(canonical_memory_dir: str | os.PathLike[str]) -> dict[str, int]:
    """Map `<store-index>/<filename>` -> mtime_ns for the CANONICAL topics dir, so
    a before/after diff isolates files the pipeline just wrote (and leaves
    historical topic files untouched, avoiding false positives).

    Canonical-only by design — see `_topic_dirs`: the writer writes canonical
    topics surgically (only proposed slugs change), while the repo mirror is a
    wholesale re-copy that can't be mtime-diffed and would flag every file."""
    snapshot: dict[str, int] = {}
    for index, topics_dir in enumerate(_topic_dirs(canonical_memory_dir)):
        if not topics_dir.is_dir():
            continue
        for path in topics_dir.glob("*.md"):
            snapshot[f"{index}/{path.name}"] = path.stat().st_mtime_ns
    return snapshot


def changed_topic_slugs(before: dict[str, int], after: dict[str, int]) -> list[str]:
    """Filenames (deduped across stores) whose content changed between snapshots."""
    names: set[str] = set()
    for key, mtime in after.items():
        if before.get(key) != mtime:
            names.add(key.split("/", 1)[1])
    return sorted(names)


def run_topic_guard(
    *,
    spec_path: str | os.PathLike[str],
    canonical_memory_dir: str | os.PathLike[str],
    before: dict[str, int],
    active_json_path: str | os.PathLike[str],
    allowlist=None,
) -> list[str]:
    """Post-run guard: validate the topic slugs written this run against the
    just-delivered spec. Returns the list of cross-spec drift violations (empty
    when in policy)."""
    after = snapshot_topics(canonical_memory_dir)
    changed = changed_topic_slugs(before, after)
    delivered_spec_id = resolve_delivered_spec_id(spec_path, active_json_path)
    return validate_topic_slugs(changed, delivered_spec_id, allowlist=allowlist)


def _append_marked_slugs(proposal: dict) -> set[str]:
    """The slug stems of every `project_topics` entry marked `append: true`.

    These are sanctioned cross-spec CLOSURE NOTES (e.g. a spec-045 deliver
    appending a note to the spec-040 topic). Their slug carries the PRIOR spec's
    number, so the recurrence guard flags them as cross-spec drift even though they
    are legitimate appends — used by `classify_drift` to reclassify them advisory
    (spec 047 AC-5)."""
    out: set[str] = set()
    for topic in proposal.get("project_topics") or []:
        if isinstance(topic, dict) and topic.get("append") is True:
            slug = topic.get("slug")
            if isinstance(slug, str) and slug:
                out.add(slug)
    return out


def classify_drift(
    drift: list[str], *, append_slugs: set[str]
) -> tuple[list[str], list[str]]:
    """Split recurrence-guard drift slugs into (advisory, failures).

    A drift slug backed by an `append: true` project topic is a sanctioned
    cross-spec CLOSURE NOTE — already written, post-hoc — so it is reclassified as
    an advisory WARN (exit 0), NOT a run-failure. A drift slug with no append
    marker is a genuine cross-spec recurrence and stays a failure (exit 26). The
    note is already on disk at this point either way; reclassification only changes
    whether the run aborts (spec 047 AC-5)."""
    advisory = sorted(s for s in drift if s in append_slugs)
    failures = sorted(s for s in drift if s not in append_slugs)
    return advisory, failures


def _prewrite_cross_spec_disposition(
    proposal: dict,
    *,
    spec_path: str | os.PathLike[str],
    active_json_path: str | os.PathLike[str],
) -> tuple[list[str], list[str]]:
    """Pre-write INTENT split of the proposal's `project_topics[].slug` set into
    (advisory, failures) against the just-delivered spec (spec 055).

    The post-write recurrence guard (`run_topic_guard`) diffs on-disk topic files
    AFTER the writer runs, so it catches a cross-spec clobber only once the
    destructive overwrite already landed. This computes the SAME cross-spec drift
    from the proposal's INTENT — the slugs the writer would create/overwrite —
    BEFORE any write, reusing `validate_topic_slugs` + `classify_drift`. An
    `append: true` cross-spec slug is the sanctioned closure-note path and is
    reclassified ADVISORY; a bare cross-spec slug is a `failures` entry (exit 26).
    Only `project_topics` slugs are scoped — `decisions` and the non-spec-prefixed
    silo/shared namespaces are cross-cutting and already ignored by
    `validate_topic_slugs`."""
    slugs = [
        topic["slug"]
        for topic in (proposal.get("project_topics") or [])
        if isinstance(topic, dict)
        and isinstance(topic.get("slug"), str)
        and topic.get("slug")
    ]
    delivered_spec_id = resolve_delivered_spec_id(spec_path, active_json_path)
    drift = validate_topic_slugs(slugs, delivered_spec_id)
    return classify_drift(drift, append_slugs=_append_marked_slugs(proposal))


def _project_slug_for(cwd: str | os.PathLike[str]) -> str:
    """Derive the canonical project slug from a cwd path.

    Per `.claude/rules/claude-code.md` "Auto-memory canonical location": the slug
    is the absolute cwd with `/` rewritten to `-` (INCLUDES the leading dash).
    The launcher runs the subprocess from the repo ROOT (spec 036 M5, AC-9), so
    this resolves to the repo-root slug — NOT a `.claude/hooks` sub-dir slug."""
    return str(cwd).replace("/", "-")


def _build_agent_options(
    repo_root: str,
    canonical_memory_dir: str,
    model_name: str,
    max_turns: int,
    workflow_prefix: str,
    options_cls=None,
):
    """Construct the `ClaudeAgentOptions` for the proposal pass (spec 040, AC-1).

    `cwd=repo_root` (absolute) pins the SDK child's working directory so the
    `memory: project` auto-scaffold lands at the repo-root-relative path the
    writer already owns -- never under `.claude/hooks/` as a nested `.claude`.
    Kept as a pure helper so the cwd wiring is unit-assertable without a live
    `query()` call. `options_cls` lets `_run` pass its locally-imported class."""
    if options_cls is None:
        from claude_agent_sdk import ClaudeAgentOptions as options_cls
    return options_cls(
        allowed_tools=["Read", "Glob", "Grep"],
        permission_mode="bypassPermissions",
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": workflow_prefix,
            "exclude_dynamic_sections": True,
        },
        setting_sources=["project"],
        settings=str(CLAUDE_ROOT / "settings.sdk-memory.json"),
        add_dirs=[canonical_memory_dir],
        model=model_name,
        max_turns=max_turns,
        cwd=str(repo_root),
    )


def _assert_no_nested_claude(repo_root: str | os.PathLike[str]) -> list[str]:
    """Post-run assertion (spec 036 M5, AC-9; spec 040 AC-4): nested `.claude`.

    035 scaffolded `.claude/.claude/` and `.claude/hooks/.claude/` because the
    subprocess ran with `cwd=.claude/hooks/`. Spec 040 pins the subprocess cwd to
    repo root, but the `memory: project` auto-scaffold can still leave an EMPTY
    nested `.claude/agent-memory/<agent>/` tree. Such a tree is benign: it holds
    no regular files. We auto-clean it (`rmtree`) and emit a structured WARN
    (surfaced, never silently swallowed -- constitution Rule 2), dropping it from
    findings so the run proceeds. A nested `.claude` with >=1 regular file is a
    REAL leak: it is retained in findings and the caller hard-fails (exit 30).
    Returns the findings list (empty == clean)."""
    claude_root = Path(repo_root) / ".claude"
    if not claude_root.is_dir():
        return []
    findings: list[str] = []
    for nested in sorted(claude_root.rglob(".claude")):
        if not nested.is_dir():
            continue
        has_regular_file = any(p.is_file() for p in nested.rglob("*"))
        if has_regular_file:
            findings.append(f"NESTED .claude dir: {nested}")
            continue
        # Benign empty auto-scaffold: rmtree targets ONLY this empty nested
        # `.claude` subtree (no regular files), never the top-level `.claude/`.
        shutil.rmtree(nested)
        print(
            f"sdk_memory nested-claude-autoclean: removed empty scaffold {nested}",
            file=sys.stderr,
        )
    return findings


def _assert_no_repo_silo_leak(repo_root: str | os.PathLike[str]) -> list[str]:
    """Post-run repo-side silo-leak scan (spec 038 M8, AC-7).

    The deterministic writer constructs ONLY canonical silo paths (silos are
    canonical-only), so a repo-side silo path should be structurally impossible.
    This is the belt-and-suspenders post-run assertion that FAILS the run (exit
    33) on any repo-side silo CONTENT — a `.md` file under a
    `<repo>/.claude/agent-memory/` tree or under a malformed nested
    `<repo>/.claude/memory/agent-memory/`. It keys on `.md` content, not bare
    directory existence: Claude Code's `memory: project` frontmatter
    auto-creates empty `<repo>/.claude/agent-memory/<agent>/` placeholder dirs at
    spawn (which is benign and expected) — the 035 LEAK was silo `.md` FILES
    (57 of them) written into the repo. Returns findings (empty list == clean).
    Surfaced, never swallowed (Rule 2)."""
    claude_root = Path(repo_root) / ".claude"
    findings: list[str] = []
    for silo_root in (claude_root / "agent-memory", claude_root / "memory" / "agent-memory"):
        if not silo_root.is_dir():
            continue
        for leaked in sorted(silo_root.rglob("*.md")):
            findings.append(
                f"REPO-SIDE SILO LEAK: {leaked} must not exist "
                f"(silos are canonical-only, never mirrored)"
            )
    return findings


def _spend_log_dir() -> Path:
    """The dir spend markers live under: the launcher-set `SDK_MEMORY_LOG_DIR`
    (gitignored `.claude/sessions/sdk-memory/`; the --smoke path points it at the
    tmp tree), else the real default. Single source for the Python sidecar + the
    launcher's composed marker."""
    override = os.environ.get("SDK_MEMORY_LOG_DIR")
    if override:
        return Path(override)
    return CLAUDE_ROOT / "sessions" / "sdk-memory"


def _write_cost_sidecar(*, cost_usd, usage, model: str) -> None:
    """Write the per-run cost sidecar `_last-run-cost.json` from the SDK result
    (spec 039 M8). Holds `{cost_usd, tokens_in, tokens_out, model}`. Token counts
    are read from the SDK `usage` mapping (`input_tokens`/`output_tokens`); a
    missing field is recorded as null (recorded-as-absent, Rule 2). The launcher
    composes this into the canonical `_last-run.json` on exit."""
    tokens_in = None
    tokens_out = None
    if isinstance(usage, dict):
        tokens_in = usage.get("input_tokens")
        tokens_out = usage.get("output_tokens")
    elif usage is not None:
        tokens_in = getattr(usage, "input_tokens", None)
        tokens_out = getattr(usage, "output_tokens", None)
    sidecar = {
        "cost_usd": cost_usd,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "model": model,
    }
    log_dir = _spend_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "_last-run-cost.json").write_text(
        json.dumps(sidecar), encoding="utf-8"
    )


def _assert_smoke_all_store(proposal: dict) -> list[str]:
    """Smoke-only all-store assertion (spec 039 M5, AC-8/AC-9).

    The 038 lesson: a real-run gate is only as good as its corpus — a green smoke
    that walked no silo and no shared_topic never exercised the agent-memory write
    path, so it could not catch agent-memory bugs. This assertion FAILS the smoke
    gate (exit 34) when the parsed proposal would not walk every store: it requires
    ≥1 silo ENTRY (a non-empty entry list under some agent) AND ≥1 shared_topic.
    Returns findings (empty list == every store walked). Surfaced, never swallowed
    (Rule 2). Gated on `SDK_MEMORY_SMOKE=1` by the caller, so a real deliver — whose
    proposal legitimately may omit a store — never runs it (anti-over-gating)."""
    findings: list[str] = []
    silos = proposal.get("silos") or {}
    silo_entry_count = sum(len(entries or []) for entries in silos.values())
    if silo_entry_count == 0:
        findings.append(
            "smoke all-store: proposal has zero silo entries — the agent-memory "
            "silo write path would not be walked"
        )
    if not (proposal.get("shared_topics") or []):
        findings.append(
            "smoke all-store: proposal has zero shared_topics — the shared "
            "agent-memory topic write path would not be walked"
        )
    return findings


def _inject_smoke_all_store(proposal: dict, worked_agents: set[str]) -> dict:
    """SMOKE-ONLY: deterministically populate the agent-memory stores so the smoke
    always walks the silo + shared write path.

    The live LLM judges the trivial 900-smoke spec as having no reusable silo or
    cross-agent craft, so it proposes `silos: {}` / `shared_topics: []` and the
    all-store assertion (exit 34) fires — even though the leak/orphan bugs that the
    smoke exists to catch live in the DETERMINISTIC writer/mirror, not the LLM.
    Rather than coax the model, this injects (ONLY-IF-ABSENT) exactly:
      - ONE silo entry for ONE deterministically-chosen WORKED agent
        (`sorted(worked_agents)[0]`, or a fixed `backend-engineer` fallback when the
        ledger resolved no worked agents) — pinned to a worked agent so the budget
        check's non-worked cap of 0 is not tripped;
      - ONE generic shared_topic.
    If the proposal ALREADY carries ≥1 silo ENTRY AND ≥1 shared_topic (a richer
    future corpus), it is returned UNTOUCHED so the real proposal is used.

    The injected entries are schema-valid (`_proposal_schema.validate_proposal`) and
    within `_budget_check` budgets (≤1 silo per worked agent, ≤1 shared). Gated by
    the SMOKE-ONLY caller in `_run` — an injected entry NEVER reaches a real deliver.
    Returns the (possibly mutated) proposal."""
    silos = proposal.get("silos") or {}
    has_silo_entry = any(entries for entries in silos.values())
    has_shared = bool(proposal.get("shared_topics") or [])
    if has_silo_entry and has_shared:
        return proposal

    # A silo's MEMORY.md index line references a SHARED-ROOT agent-memory/topics/
    # file (not a nested per-agent topic). The injected silo entry must point at a
    # shared topic slug that actually lands on disk — otherwise the silo orphan
    # check would flag a DEAD LINK. Default to the injected shared slug; if the
    # proposal already carried shared topics, reuse the first existing one.
    shared_slug = "smoke-shared-craft"

    if not has_shared:
        proposal["shared_topics"] = [
            {
                "slug": shared_slug,
                "title": "Smoke shared craft note",
                "hook": "deterministic smoke injection exercises the shared write path",
                "body": "Generic cross-agent craft note injected SMOKE-ONLY so the "
                "smoke gate always walks the shared agent-memory write path.",
            }
        ]
    else:
        shared_slug = (proposal["shared_topics"][0] or {}).get("slug", shared_slug)

    if not has_silo_entry:
        agent = sorted(worked_agents)[0] if worked_agents else "backend-engineer"
        silos = dict(silos)
        silos[agent] = [
            {
                "title": "Smoke craft note",
                "topic_slug": shared_slug,
                "hook": "deterministic smoke injection exercises the silo write path",
            }
        ]
        proposal["silos"] = silos

    return proposal


async def _run(spec_path: str, session_id: str | None = None) -> int:
    # Local import so build_proposal_prompt can be exercised without the SDK installed.
    from claude_agent_sdk import ClaudeAgentOptions, query
    from claude_agent_sdk import CLIConnectionError, ResultMessage

    # Slug per .claude/rules/claude-code.md "Auto-memory canonical location" — INCLUDES leading dash.
    # The launcher cd's to the repo root (spec 036 M5), so getcwd() is the repo root.
    project_slug = _project_slug_for(os.getcwd())
    canonical_memory_dir = os.path.expanduser(f"~/.claude/projects/{project_slug}")
    # Smoke gate (spec 038 M8): the `--smoke` launcher mode points the canonical
    # store and the repo root at a tmp tree so the real run NEVER touches the real
    # store. These overrides are set ONLY by the launcher's --smoke path.
    canonical_override = os.environ.get("SDK_MEMORY_CANONICAL_OVERRIDE")
    if canonical_override:
        canonical_memory_dir = canonical_override
    repo_root = Path(os.environ.get("SDK_MEMORY_REPO_OVERRIDE") or REPO_ROOT)
    claude_root = repo_root / ".claude"
    # Smoke gate (spec 038 M8): the `--smoke` mode points the session at a SYNTHETIC
    # transcript committed under the smoke corpus, so the proposal pass reads a fake
    # conversation about the 900-smoke corpus — NOT the real live session (which is
    # about whatever real spec is in flight and would drift the topic-slug guard).
    # The override resolves the session JSONL from the (already-overridden) canonical
    # dir, so the smoke is fully self-contained: corpus + matching session.
    session_override = os.environ.get("SDK_MEMORY_SESSION_OVERRIDE")
    if session_override:
        session_id = session_override
    # Smoke flag (spec 038 M8 + spec 039 M5): set ONLY by the `--smoke` launcher
    # mode. It gates OUT the cross-spec topic-slug recurrence guard (exit 26), which
    # is inherently a real-deliver-only check: a synthetic-spec smoke run inside the
    # real repo cannot avoid reading the real workflow docs, so the live LLM proposes
    # a topic slug for the REAL in-flight spec, which the recurrence guard would
    # (correctly, for a real deliver) reject as cross-spec drift. It ALSO gates IN
    # the smoke-only all-store assertion (exit 34): the smoke proposal MUST walk
    # every store (≥1 silo entry + ≥1 shared_topic) so the gate always exercises the
    # agent-memory write path. Every OTHER post-write check stays active in smoke.
    smoke_mode = os.environ.get("SDK_MEMORY_SMOKE") == "1"
    workflow_prefix = _workflow_system_prompt()

    # LLM half is a single read-once pass: Read/Glob/Grep ONLY — NO Write/Edit.
    # The deterministic writer (in-process Python, not a tool call) owns every
    # file write, so the LLM half structurally cannot write a memory file (Rule 5).
    model_name = os.environ.get("SDK_MEMORY_MODEL", "opus")
    options = _build_agent_options(
        repo_root=str(repo_root),
        canonical_memory_dir=canonical_memory_dir,
        model_name=model_name,
        max_turns=int(os.environ.get("SDK_MEMORY_MAX_TURNS", "100")),
        workflow_prefix=workflow_prefix,
        options_cls=ClaudeAgentOptions,
    )

    proposal_prompt = build_proposal_prompt(
        spec_path, session_id, canonical_dir=canonical_memory_dir, repo_root=repo_root
    )

    skill_path = (
        CLAUDE_ROOT / "skills" / "memory" / "extraction-learnings" / "SKILL.md"
    )
    active_json_path = CLAUDE_ROOT / "active.json"
    # Pre-write snapshots — the whole-store topic-recurrence guard runs post-write.
    topics_before = snapshot_topics(canonical_memory_dir)

    # A terminal SDK condition short-circuits the run with the mapped exit code
    # (rate-limit 20, connection 21, max_turns 24, import 11).
    terminal: dict[str, int] = {}
    result_text = ""

    async def _read_once() -> None:
        nonlocal result_text
        async for msg in query(prompt=proposal_prompt, options=options):
            if isinstance(msg, ResultMessage):
                api_error_status = getattr(msg, "api_error_status", None)
                if api_error_status == 429:
                    terminal["code"] = 20
                    return
                usage = getattr(msg, "usage", None)
                if usage is not None:
                    print(f"sdk_memory usage: {usage}", file=sys.stderr)
                # Cost sidecar (spec 039 M8, AC-15): Python alone holds the
                # ResultMessage, so it records the live cost/token half to a sidecar
                # the launcher composes into _last-run.json. Best-effort: a sidecar
                # write failure is logged, never fatal (Rule 2 — surfaced).
                try:
                    _write_cost_sidecar(
                        cost_usd=getattr(msg, "total_cost_usd", None),
                        usage=usage,
                        model=model_name,
                    )
                except OSError as exc:
                    print(f"sdk_memory: cost sidecar write failed: {exc}", file=sys.stderr)
                if msg.result is not None:
                    result_text = msg.result
                    print(msg.result)
                    try:
                        added = _append_learning(msg.result, skill_path)
                        if added:
                            print(
                                f"sdk_memory: appended {added} novel learning(s) to {skill_path}",
                                file=sys.stderr,
                            )
                    except OSError as exc:
                        print(f"sdk_memory: learning append failed: {exc}", file=sys.stderr)

    try:
        await _read_once()
    except CLIConnectionError:
        terminal.setdefault("code", 21)
    except ImportError:
        terminal.setdefault("code", 11)
    except Exception as exc:  # noqa: BLE001 — map terminal SDK conditions, surface the rest
        if "maximum number of turns" in str(exc):
            terminal.setdefault("code", 24)
        else:
            raise

    if "code" in terminal:
        return terminal["code"]

    # Schema-validate the proposal (spec 038 M1). A missing/malformed proposal or
    # any schema violation is a deterministic terminal failure -> exit 31 (not
    # swallowed, Rule 2; not retried — a re-run would re-produce the same shape).
    proposal = parse_proposal(result_text)
    if proposal is None:
        print(
            "sdk_memory: LLM half returned no parseable proposal JSON; "
            "nothing written (exit 31)",
            file=sys.stderr,
        )
        return 31
    schema_findings = _proposal_schema_validate(proposal, canonical_memory_dir)
    if schema_findings:
        for finding in schema_findings:
            print(f"sdk_memory proposal-schema: {finding}", file=sys.stderr)
        return 31

    # Soft memory-vs-queue boundary guard (spec 047 AC-6b): outer-memory entries
    # framed as deferred work belong in workflow/queue.md, not memory/. Advisory —
    # surfaced as a WARN (Rule 2), the proposal still writes (NOT exit 31).
    from _proposal_schema import validate_memory_queue_boundary

    for warning in validate_memory_queue_boundary(proposal):
        print(f"sdk_memory WARN proposer-queue-boundary: {warning}", file=sys.stderr)

    # Resolve worked agents (deterministic phase-ledger map, NOT LLM judgement)
    # BEFORE both the smoke injection and the writer: the injection MUST pin its one
    # silo entry to a worked agent (else the budget check's non-worked-cap-0 would
    # flag it), and the writer consumes the same set.
    worked = _resolve_worked_agents(spec_path, session_id, canonical_memory_dir)

    # Smoke-only deterministic all-store injection (spec 039 follow-up): the live
    # LLM judges the trivial 900-smoke spec as having no silo/shared craft, so it
    # proposes empty silos/shared_topics and the all-store assertion (exit 34)
    # would fire even though the leak/orphan bugs it guards live in the
    # DETERMINISTIC writer/mirror. Rather than coax the LLM, the smoke walks the
    # agent-memory write path deterministically: inject exactly ONE worked-agent
    # silo entry + ONE shared_topic when the proposal lacks them (only-if-absent,
    # so a richer future corpus's real proposal is used untouched). SMOKE-ONLY —
    # gated on the smoke flag, so an injected entry NEVER reaches a real deliver's
    # canonical store. The exit-34 assertion below then becomes a true safety net:
    # it fires only if injection somehow failed to populate the stores.
    if smoke_mode:
        proposal = _inject_smoke_all_store(proposal, worked)

    # Smoke-only all-store assertion (spec 039 M5, AC-8/AC-9): under --smoke ONLY,
    # the proposal MUST walk every store (≥1 silo entry AND ≥1 shared_topic) so the
    # gate always exercises the agent-memory write path (the 038 lesson). Runs AFTER
    # the smoke injection (so it is a safety net — it fires only if injection failed)
    # and BEFORE the writer so a store-omitting proposal fails before any write (exit
    # 34, terminal, non-retried). Gated strictly on the smoke flag — a real deliver
    # (whose proposal may legitimately omit a store) never runs it (anti-over-gating).
    if smoke_mode:
        all_store_findings = _assert_smoke_all_store(proposal)
        if all_store_findings:
            for finding in all_store_findings:
                print(f"sdk_memory smoke all-store: {finding}", file=sys.stderr)
            return 34

    # Deterministic writer (spec 038 M3/M4). Owns every path, the MEMORY.md
    # index-line shape, the canonical-vs-repo split, the personal-line filter, and
    # the per-store TRUNCATING CAP — it writes the first N per store and drops + logs
    # the excess (a normal bounded write, exit 0; no abort). This is in-process
    # Python, not a Write/Edit tool call — the SDK actor remains the sole memory writer.
    from _memory_writer import write_proposal

    # Pre-write cross-spec INTENT guard (spec 055). The post-write recurrence guard
    # below catches a cross-spec clobber only AFTER the destructive write lands; this
    # rejects a bare cross-spec `project_topics` slug BEFORE any write, so NOTHING is
    # written to either store. Reuses exit 26 (no new exit code). Skipped in --smoke
    # ONLY (real-deliver-only check, exactly like the post-write guard): the live
    # smoke LLM proposes a topic for the REAL in-flight spec, which is cross-spec to
    # the synthetic smoke spec and would wrongly abort --smoke. The skip is EXPLICIT
    # and logged, never silent (Rule 2).
    if smoke_mode:
        print(
            "sdk_memory smoke: pre-write cross-spec intent guard skipped "
            "(real-deliver-only check)",
            file=sys.stderr,
        )
    else:
        intent_advisory, intent_failures = _prewrite_cross_spec_disposition(
            proposal, spec_path=spec_path, active_json_path=active_json_path
        )
        if intent_advisory:
            delivered = resolve_delivered_spec_id(spec_path, active_json_path)
            print(
                "sdk_memory WARN: pre-write intent guard saw cross-spec append "
                f"closure-note(s) for delivered spec {delivered!r} (advisory, "
                f"proceeding to write): {', '.join(intent_advisory)}",
                file=sys.stderr,
            )
        if intent_failures:
            delivered = resolve_delivered_spec_id(spec_path, active_json_path)
            print(
                "sdk_memory: pre-write intent guard rejected cross-spec "
                f"project_topics slug(s) for delivered spec {delivered!r} before any "
                f"write (nothing written): {', '.join(intent_failures)}",
                file=sys.stderr,
            )
            return 26

    written = write_proposal(
        proposal,
        canonical_dir=canonical_memory_dir,
        repo_dir=claude_root,
        worked_agents=worked,
    )
    if written:
        print(f"sdk_memory: writer wrote {len(written)} file(s)", file=sys.stderr)

    # Deliver-time silo landing POST-CHECK (spec 047 M3, AC-2): a reported silo
    # path MUST exist at the auto-load location. Closes the silent no-op where the
    # writer counted a silo it never landed (exit 0 + count was NOT a landing
    # signal). Any reported-but-absent silo fails the run -> exit 35 (surfaced,
    # never swallowed: Rule 2).
    from _memory_writer import assert_silos_landed

    silo_absent = assert_silos_landed(written, canonical_dir=canonical_memory_dir)
    if silo_absent:
        for finding in silo_absent:
            print(f"sdk_memory silo-post-check: {finding}", file=sys.stderr)
        return EXIT_SILO_ABSENT

    # Mechanical silo-shape check (spec 036 M4, AC-8). Any nested
    # agent-memory/<agent>/topics/ path fails the run -> exit 30.
    shape_findings = _run_silo_shape_check(canonical_memory_dir)
    if shape_findings:
        for finding in shape_findings:
            print(f"sdk_memory silo-shape-check: {finding}", file=sys.stderr)
        # Exit 30 is intentionally shared by the two structural-shape violations:
        # this silo-shape check (AC-8) and the nested-.claude check below (AC-9).
        return 30

    # Cross-spec topic-slug recurrence guard (exit 26). Skipped in --smoke ONLY
    # (real-deliver-only check — see smoke_mode comment above). The skip is EXPLICIT
    # and logged, never silent (Rule 2). Every other post-write check still runs.
    if smoke_mode:
        print(
            "sdk_memory smoke: cross-spec recurrence guard skipped "
            "(real-deliver-only check)",
            file=sys.stderr,
        )
    else:
        drift = run_topic_guard(
            spec_path=spec_path,
            canonical_memory_dir=canonical_memory_dir,
            before=topics_before,
            active_json_path=active_json_path,
        )
        if drift:
            delivered = resolve_delivered_spec_id(spec_path, active_json_path)
            # Spec 047 AC-5: a drift slug backed by an `append: true` project topic
            # is a sanctioned cross-spec CLOSURE NOTE (already written, post-hoc) —
            # advisory WARN, NOT a run-failure. Only genuine drift (no append marker)
            # aborts with exit 26.
            advisory, failures = classify_drift(
                drift, append_slugs=_append_marked_slugs(proposal)
            )
            if advisory:
                print(
                    "sdk_memory WARN: topic-slug recurrence guard saw cross-spec "
                    f"append closure-note(s) for delivered spec {delivered!r} "
                    f"(advisory, already written): {', '.join(advisory)}",
                    file=sys.stderr,
                )
            if failures:
                print(
                    "sdk_memory: topic-slug recurrence guard rejected cross-spec "
                    f"slug(s) for delivered spec {delivered!r}: {', '.join(failures)}",
                    file=sys.stderr,
                )
                return 26

    # Post-run repo-side silo-leak scan (spec 038 M8, AC-7): belt-and-suspenders
    # over the writer's structural canonical-only guarantee. Any repo-side silo
    # path fails the run -> exit 33 (not swallowed, Rule 2). Runs BEFORE the orphan
    # check (spec 039 M4, AC-6): a repo-side agent-memory leak that is ALSO an
    # orphan must be REPORTED as a leak (33), not masked as an orphan (27) — the
    # 038 diagnostic pointed at the wrong fault because orphan ran first.
    leak_findings = _assert_no_repo_silo_leak(repo_root)
    if leak_findings:
        for finding in leak_findings:
            print(f"sdk_memory repo-silo-leak: {finding}", file=sys.stderr)
        return 33

    # Post-run cwd assertion (spec 036 M5, AC-9): the subprocess runs from the
    # repo root, so no nested `.claude` dir should have been scaffolded. A nested
    # dir reuses exit 30 (a structural-shape violation, like the silo-shape check).
    nested_findings = _assert_no_nested_claude(repo_root)
    if nested_findings:
        for finding in nested_findings:
            print(f"sdk_memory nested-claude-check: {finding}", file=sys.stderr)
        return 30

    orphan_findings = _run_orphan_check(canonical_memory_dir, claude_root)
    if orphan_findings:
        for finding in orphan_findings:
            print(f"sdk_memory orphan-check: {finding}", file=sys.stderr)
        return 27

    return 0


def _resolve_worked_agents(spec_path: str, session_id: str | None, canonical_dir) -> set[str]:
    """Resolve the silo agents that worked the spec from its phase ledger.

    Deterministic (NOT LLM judgement): maps each phase in `state.json.phase_history`
    to its owning silo agent (`_budget_check._PHASE_AGENTS`). Returns the empty set
    when the ledger cannot be built (e.g. no state.json) — the budget check then
    flags ANY silo touch, the conservative safe default."""
    from _budget_check import resolve_worked_agents

    spec_dir = Path(spec_path).resolve()
    state_path = spec_dir / "state.json"
    if not state_path.is_file():
        return set()
    actor_map: dict = {}
    if session_id and canonical_dir is not None:
        try:
            from _actor_map import build_actor_map

            actor_map = build_actor_map(
                canonical_dir=canonical_dir,
                orchestrator_session_id=session_id,
                team_config_path=_resolve_team_config_path(spec_dir),
            )
        except Exception as exc:  # noqa: BLE001 — actor map is best-effort; phase set is what matters
            # Surface the swallowed failure (Rule 2): the worked-agent set is
            # resolved from the phase ledger alone, so a degraded actor map does
            # not empty it — but a silent swallow hid that fact during diagnosis.
            print(
                f"sdk_memory WARN: actor_map build failed: {exc}", file=sys.stderr
            )
            actor_map = {}
    from _phase_ledger import build_phase_ledger

    ledger = build_phase_ledger(state_path, actor_map)
    return resolve_worked_agents(ledger)


def _proposal_schema_validate(
    proposal, canonical_memory_dir: str | os.PathLike[str] | None = None
) -> list[str]:
    """Validate the LLM-half proposal against the pure STRUCTURAL schema (spec 038
    M1). A non-empty finding list maps to pipeline exit 31 (surfaced, never
    swallowed: Rule 2). The writer consumes ONLY a structurally-valid proposal.

    The existing canonical `agent-memory/topics/` slug-set is still enumerated here
    and threaded to the pure validator for signature stability, but spec 042 moved
    the silo `topic_slug` RESOLUTION check OUT of the validator: an unresolved slug
    is now a writer-recoverable drop (`_memory_writer._drop_dead_silo_lines`), not an
    exit-31 finding. Exit 31 stays reserved for structural invalidity (missing keys,
    wrong types, nested `/`). The validator stays file-I/O-free."""
    from _proposal_schema import validate_proposal

    from _memory_writer import agent_memory_base

    existing_canonical_slugs: frozenset[str] = frozenset()
    if canonical_memory_dir is not None:
        shared_topics_dir = agent_memory_base(canonical_memory_dir) / "topics"
        if shared_topics_dir.is_dir():
            existing_canonical_slugs = frozenset(
                p.stem for p in shared_topics_dir.glob("*.md")
            )
    return validate_proposal(proposal, existing_canonical_slugs)


def _run_silo_shape_check(canonical_memory_dir: str | os.PathLike[str]) -> list[str]:
    """Mechanical silo-shape check (spec 036 M4, AC-8).

    Deterministic on-disk path scan: any nested `agent-memory/<agent>/topics/`
    path fails the run (exit 30). Per-agent silo folders hold only `MEMORY.md`;
    all topic bodies live at the ROOT `agent-memory/topics/`."""
    from _silo_shape_check import check_silo_shape
    from _memory_writer import agent_memory_base

    return check_silo_shape(agent_memory_base(canonical_memory_dir))


def _run_orphan_check(
    canonical_memory_dir: str | os.PathLike[str],
    repo_claude_root: str | os.PathLike[str] | None = None,
) -> list[str]:
    """Mechanical post-write orphan/dead-link backstop (spec 035 M4 / spec 036 M3).

    Runs the deterministic `_orphan_check.check_store` on BOTH outer `memory/`
    stores (canonical + repo mirror) AND extends over the canonical-only silo
    stores (spec 036 AC-11): the shared `agent-memory/topics/` store and each
    per-agent silo index. A mid-kill that half-indexes a silo is caught here.
    Returns the flattened findings; a non-empty list surfaces as pipeline exit 27
    (not swallowed — Rule 2). `repo_claude_root` defaults to the real `CLAUDE_ROOT`;
    the `--smoke` run passes the tmp `.claude` root so the smoke mirror is checked."""
    from _orphan_check import check_store, check_silo_store
    from _memory_writer import agent_memory_base

    repo_root = Path(repo_claude_root) if repo_claude_root is not None else CLAUDE_ROOT
    findings: list[str] = []

    # Outer memory/ stores (canonical + repo mirror).
    for store in (Path(canonical_memory_dir) / "memory", repo_root / "memory"):
        if (store / "MEMORY.md").is_file():
            findings.extend(check_store(store))

    # Silo stores (canonical-only). Shared topics live at the ROOT
    # agent-memory/topics/; each agent folder holds only a MEMORY.md index.
    # The base is UNDER the auto-memory root memory/ (spec 047 AC-1).
    agent_memory = agent_memory_base(canonical_memory_dir)
    shared_topics = agent_memory / "topics"
    # Shared store is an outer-shaped store IF it carries its own MEMORY.md index;
    # otherwise its topics are only referenced from silo indexes (checked below).
    if (agent_memory / "MEMORY.md").is_file():
        findings.extend(check_store(agent_memory))
    for agent in SILO_AGENTS:
        agent_dir = agent_memory / agent
        if (agent_dir / "MEMORY.md").is_file():
            findings.extend(check_silo_store(agent_dir, shared_topics))
    return findings


def _resolve_spec_path() -> str:
    if len(sys.argv) >= 2 and sys.argv[1]:
        return sys.argv[1]
    env_path = os.environ.get("SPEC_PATH")
    if env_path:
        return env_path
    raise SystemExit("sdk_memory_pipeline: spec path required as argv[1] or SPEC_PATH env")


def _resolve_session_id(argv: list[str] | None = None, env: dict[str, str] | None = None) -> str | None:
    """Resolve the orchestrator session ID.

    Precedence: `argv[2]` wins over `ORCHESTRATOR_SESSION_ID` env var. Returns
    None when neither source provides a non-empty value — the launcher's
    exit-25 guard catches the empty case before Python sees it in practice,
    so a None here means the caller is running Python directly without the
    launcher (test or ad-hoc invocation).
    """
    argv = argv if argv is not None else sys.argv
    env = env if env is not None else os.environ
    if len(argv) >= 3 and argv[2]:
        return argv[2]
    env_sid = env.get("ORCHESTRATOR_SESSION_ID")
    if env_sid:
        return env_sid
    return None


def main() -> int:
    spec_path = _resolve_spec_path()
    session_id = _resolve_session_id()
    try:
        return asyncio.run(_run(spec_path, session_id))
    except ImportError:
        return 11


if __name__ == "__main__":
    sys.exit(main())

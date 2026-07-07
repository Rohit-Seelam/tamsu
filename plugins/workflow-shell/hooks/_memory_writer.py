"""Deterministic memory writer for the SDK memory pipeline (spec 038 M3/M4/M5).

The propose→write pivot has the LLM half return a schema-valid PROPOSAL (touching
no files); this module is the deterministic Python writer that consumes it and
OWNS every written path, the `MEMORY.md` index-line shape, the per-store TRUNCATING
CAP (write the first N per store, drop + log the excess — never abort), the
canonical-vs-repo split, and personal-line filtering. Same proposal in →
byte-identical files out.

This is in-process Python invoked by the SDK-actor subprocess — NOT a Write/Edit
tool call — so the SDK actor remains the sole memory writer (Constitution Rule 5).
It is in the `_orphan_check.py` / `_budget_check.py` mould: deterministic, pure of
LLM judgement, separate from content generation.

Determinism contract:
  - inputs are iterated in SORTED order (no dict-insertion-order dependence);
  - the writer controls every body it emits and writes NO timestamps into
    writer-controlled files (the `decisions.md` / topic / index shapes are pure
    functions of the proposal);
  - the canonical store is written first, then the non-personal subset is mirrored
    into the repo.

Caps & worked-agent resolution reuse `_budget_check` limits (NOT re-defined here).
Personal/canonical-only filtering reuses `sdk_memory_pipeline._PERSONAL_EXCLUDE`
and the mechanical `_mirror_canonical_to_repo` mirror (single source of truth).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from _budget_check import (
    DECISIONS_LIMIT,
    SHARED_TOPICS_LIMIT,
    SILO_AGENTS,
    SILO_LIMIT,
    SPEC_TOPICS_LIMIT,
)

_INDEX_CAP_LINES = 200
_INDEX_CAP_BYTES = 25 * 1024


def agent_memory_base(canonical_dir: str | os.PathLike[str]) -> Path:
    """The canonical agent-memory root: `<canonical>/memory/agent-memory`.

    Single source of truth for the silo/shared base (spec 047 AC-1). It lives
    UNDER the auto-memory root `memory/` — the directory `memory: project`
    frontmatter auto-loads — NOT at the `<canonical>/agent-memory/` sibling,
    which is never auto-loaded (the silent silo no-op fixed in spec 047)."""
    return Path(canonical_dir) / "memory" / "agent-memory"


def assert_silos_landed(
    written: list[str], *, canonical_dir: str | os.PathLike[str]
) -> list[str]:
    """Post-write landing POST-CHECK (spec 047 AC-2): every silo path the writer
    REPORTED in `written` must actually exist on disk under the canonical store.

    Closes the silent silo no-op: pre-047 the writer counted a silo path in its
    return list while the file landed at the un-auto-loaded `<canonical>/agent-memory/`
    sibling (or was dropped), so an exit-0 `wrote N file(s)` count was NOT a landing
    signal. This re-checks PRESENCE — any reported `memory/agent-memory/...` path
    that is absent is a finding (the pipeline maps a non-empty list to a dedicated
    non-zero exit, surfaced never swallowed: Rule 2). Repo-mirror entries
    (`repo:` prefix) and non-silo paths are not silo landings and are skipped."""
    canonical = Path(canonical_dir)
    findings: list[str] = []
    for rel in written:
        if rel.startswith("repo:"):
            continue
        parts = Path(rel).parts
        if not (len(parts) >= 2 and parts[0] == "memory" and parts[1] == "agent-memory"):
            continue
        if not (canonical / rel).is_file():
            findings.append(
                f"SILO ABSENT: writer reported {rel} but no file exists at "
                f"{canonical / rel} (auto-load location)"
            )
    return sorted(findings)


# A `MEMORY.md` index line links to `](topics/<slug>.md)`. We key merge by that
# link target so a re-proposed slug UPDATES its line rather than duplicating it,
# and every OTHER existing line (incl. personal lines) is preserved verbatim.
_INDEX_LINK_RE = re.compile(r"\]\(topics/([^()/\s]+)\.md\)")


def _render_index(header: str, lines: list[str]) -> str:
    """Render a `MEMORY.md`-shaped index respecting the 200-line / 25KB caps.

    Newest overflow entries are dropped from the rendered index (the topic bodies
    they reference are unaffected), mirroring `build_silo_index` cap discipline."""
    def _body(body_lines: list[str]) -> str:
        return "\n".join([header, "", *body_lines]) + "\n" if body_lines else header + "\n"

    rendered = _body(lines)
    while lines and (
        len(rendered.splitlines()) > _INDEX_CAP_LINES
        or len(rendered.encode("utf-8")) > _INDEX_CAP_BYTES
    ):
        lines.pop()
        rendered = _body(lines)
    return rendered


def _line_slug(line: str) -> str | None:
    """The FIRST `topics/<slug>.md` link target of an index line, or None.

    Used for merge-keying (a line's primary slug). For the FULL set of links a
    line carries (merged/also-lines reference several), use `_line_slugs`."""
    match = _INDEX_LINK_RE.search(line)
    return match.group(1) if match else None


def _line_slugs(line: str) -> list[str]:
    """EVERY `topics/<slug>.md` link target on a line, in order.

    A compacted line may carry several links (`- [A](topics/a.md) — also:
    [b](topics/b.md), [c](topics/c.md)` or `- Superseded: [x](topics/x.md), …`).
    The orphan check matches on the `](topics/<file>.md)` substring across the
    whole file, so every slug on a line counts as a live reference — this is the
    invariant compaction must preserve (spec 047 fix-round 2)."""
    return _INDEX_LINK_RE.findall(line)


_SPEC_SLUG_RE = re.compile(r"^(spec-\d+)-")
_SUPERSEDED_HEADER = "Superseded:"


def _spec_prefix(slug: str | None) -> str | None:
    """The `spec-<NNN>` prefix of a slug, or None if the slug is not spec-bound.

    `spec-014-completion` → `spec-014`; `sdk-permission-model` → None."""
    if slug is None:
        return None
    match = _SPEC_SLUG_RE.match(slug)
    return match.group(1) if match else None


def _link(slug: str) -> str:
    """A bare `[slug](topics/slug.md)` link fragment (no leading bullet)."""
    return f"[{slug}](topics/{slug}.md)"


def compact_index_lines(lines: list[str]) -> list[str]:
    """Compact a `MEMORY.md` index body (spec 047 AC-6a) WITHOUT dropping any
    reference to a topic file (fix-round 2 — the line-drop version orphaned 7
    files). Done by the SDK writer, NEVER the orchestrator (Rule 5). The invariant:
    every `topics/<file>.md` referenced before compaction is still referenced after
    (the orphan check matches `](topics/<file>.md)` substrings across the whole
    file, so merging links onto ONE line preserves every reference). Two rules,
    order-preserving:

      1. SUPERSEDED lines → merged into ONE trailing `- Superseded: [a](topics/a.md),
         [b](topics/b.md), …` line. Each superseded line's links are all carried; the
         prose hooks are dropped (the body files are unaffected).
      2. Multi-line `spec-<NNN>-*` collapse → the FIRST line for that spec is kept as
         the representative; any LATER line for the same spec that references DIFFERENT
         file(s) has its links folded into the representative as
         `… — also: [x](topics/x.md), [y](topics/y.md)`. A later line that references
         only files already on the representative is dropped (no reference lost).

    Non-spec lines (cross-cutting topics, personal lines, the `decisions.md` line)
    pass through verbatim. Silo craft slugs are not `spec-<NNN>-*` shaped, so the
    collapse is a natural no-op there; SUPERSEDED merging still applies.

    Idempotent: re-running on already-compacted output is a fixed point — the single
    `Superseded:` line has no `SUPERSEDED` marker token, and each spec already has one
    representative line, so nothing further merges or drops."""
    superseded_slugs: list[str] = []
    seen_superseded: set[str] = set()
    spec_rep_pos: dict[str, int] = {}  # spec prefix -> index in `out`
    out: list[str] = []

    for line in lines:
        if "SUPERSEDED" in line:
            for slug in _line_slugs(line):
                if slug not in seen_superseded:
                    seen_superseded.add(slug)
                    superseded_slugs.append(slug)
            continue

        prefix = _spec_prefix(_line_slug(line))
        if prefix is not None and prefix in spec_rep_pos:
            rep_idx = spec_rep_pos[prefix]
            rep_slugs = set(_line_slugs(out[rep_idx]))
            extra = [s for s in _line_slugs(line) if s not in rep_slugs]
            if extra:
                out[rep_idx] = _fold_also(out[rep_idx], extra)
            # else: every link already present on the representative — drop, no loss.
            continue

        if prefix is not None:
            spec_rep_pos[prefix] = len(out)
        out.append(line)

    if superseded_slugs:
        out.append(
            f"- {_SUPERSEDED_HEADER} " + ", ".join(_link(s) for s in superseded_slugs)
        )
    return out


def _fold_also(rep_line: str, extra_slugs: list[str]) -> str:
    """Fold `extra_slugs` into a representative spec line as an `also:` clause,
    extending an existing `also:` rather than nesting a second one. Preserves every
    link already on the line (invariant)."""
    also = ", ".join(_link(s) for s in extra_slugs)
    if " — also: " in rep_line:
        return rep_line + ", " + also
    return rep_line + " — also: " + also


def _first_heading_title(topic_md: Path, slug: str) -> str:
    """The topic file's first `# Heading` text, used as a regenerated index-line
    title during self-heal. Falls back to the slug when no heading is found or the
    file cannot be read (best-effort, never raises — Rule 2: surfaced as a fallback,
    not swallowed silently — the heal itself is logged by the caller)."""
    try:
        for raw in topic_md.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                if title:
                    return title
    except OSError:
        pass
    return slug


def self_heal_index(index_text: str, topics_dir: Path, header: str) -> tuple[str, list[str]]:
    """Append a regenerated reference line for every `topics/<file>.md` that exists
    on disk but is referenced ZERO times in `index_text` (spec 047 fix-round 2).

    Runs BEFORE the orphan check so a file with no surviving reference (e.g. the 7
    that the line-drop compaction orphaned) is deterministically re-indexed on the
    next write, in BOTH canonical and mirror. Idempotent with compaction: it ONLY
    adds when the reference count is zero, and compaction NEVER removes the last
    reference — so the pair reaches a fixed point (no add/drop loop). Returns
    (healed_text, healed_slugs)."""
    if not topics_dir.is_dir():
        return index_text, []
    referenced = set(_INDEX_LINK_RE.findall(index_text))
    body = _split_index_body(index_text, header)
    healed: list[str] = []
    for topic in sorted(topics_dir.glob("*.md")):
        slug = topic.stem
        if slug in referenced:
            continue
        title = _first_heading_title(topic, slug)
        body.append(_index_line(title, slug, "auto-reindexed (self-heal)"))
        healed.append(slug)
    if not healed:
        return index_text, []
    return _render_index(header, body), healed


def _existing_index_lines(memory_md: Path, header: str) -> list[str]:
    """Read the body index lines (every line after the header + blank), preserving
    order and content. Returns [] when the file is absent. The header line and a
    single blank separator are dropped; all remaining non-empty lines are kept,
    so personal lines and prose survive a merge untouched."""
    if not memory_md.is_file():
        return []
    text = memory_md.read_text(encoding="utf-8")
    lines = text.splitlines()
    if lines and lines[0].strip() == header.strip():
        lines = lines[1:]
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    return [ln for ln in lines if ln.strip() != ""]


def _merge_index(memory_md: Path, header: str, new_lines: list[str]) -> str:
    """Merge `new_lines` into the existing index at `memory_md`, NEVER replacing it.

    For each new line: if its `topics/<slug>.md` slug already has a line, UPDATE
    that line in place; otherwise APPEND it. Every other existing line (incl.
    personal index lines and non-topic lines) is preserved. The render respects
    the 200-line / 25KB caps. Determinism: same existing file + same new_lines →
    same output."""
    merged = list(_existing_index_lines(memory_md, header))
    slug_to_pos: dict[str, int] = {}
    for pos, line in enumerate(merged):
        slug = _line_slug(line)
        if slug is not None:
            slug_to_pos[slug] = pos
    for line in new_lines:
        slug = _line_slug(line)
        if slug is not None and slug in slug_to_pos:
            merged[slug_to_pos[slug]] = line
        else:
            if slug is not None:
                slug_to_pos[slug] = len(merged)
            merged.append(line)
    # Compact the merged index on every write (spec 047 AC-6a): drop SUPERSEDED
    # lines and collapse multi-entry specs. SDK-writer-only (Rule 5).
    return _render_index(header, compact_index_lines(merged))


def _drop_dead_silo_lines(
    merged_text: str, header: str, resolvable_slugs: frozenset[str]
) -> tuple[str, list[str]]:
    """Drop every silo index line whose `topics/<slug>.md` target is dead — i.e.
    the slug is neither written in THIS proposal nor present on disk (spec 041
    AC-2). Operates on the FINAL merged text so it catches BOTH new lines AND
    lines carried forward by `_merge_index` (the carry-forward trap: `_merge_index`
    re-reads + preserves existing lines, so filtering only `new_silo_lines` would
    miss a pre-seeded dead line). `_merge_index` stays a pure merge helper with no
    filesystem awareness — Option (a) per tasks.md §T2.B. Returns (filtered_text,
    dropped_slugs)."""
    kept: list[str] = []
    dropped: list[str] = []
    for line in _split_index_body(merged_text, header):
        slug = _line_slug(line)
        if slug is not None and slug not in resolvable_slugs:
            dropped.append(slug)
        else:
            kept.append(line)
    return _render_index(header, kept), dropped


def _split_index_body(text: str, header: str) -> list[str]:
    """The non-empty body lines of an already-rendered index (header + blank
    separator stripped), mirroring `_existing_index_lines` parsing for in-memory
    text rather than a file."""
    lines = text.splitlines()
    if lines and lines[0].strip() == header.strip():
        lines = lines[1:]
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    return [ln for ln in lines if ln.strip() != ""]


def _index_line(title: str, slug: str, hook: str) -> str:
    return f"- [{title}](topics/{slug}.md) — {hook}"


def _topic_body(title: str, body: str) -> str:
    """A topic file body. Pure function of the proposal entry (no timestamps)."""
    return f"# {title}\n\n{body.rstrip(chr(10))}\n"


_DECISIONS_HEADER = "# Decisions"


def _decision_entry(d: dict) -> list[str]:
    """The rendered lines for ONE decision (no header). Pure: no timestamps."""
    title = d.get("title", "")
    hook = d.get("hook", "")
    body = d.get("body", "").rstrip("\n")
    parts: list[str] = [f"## {title}", ""]
    if hook:
        parts.append(f"_{hook}_")
        parts.append("")
    parts.append(body)
    return parts


def _append_decisions(decisions_md: Path, decisions: list[dict]) -> str:
    """APPEND the proposal's decision(s) to the existing `decisions.md`, NEVER
    rewriting it. Reads the current body, appends each new decision (sorted by
    title for stable ordering within this batch), and returns the merged text.
    When the file is absent it is seeded with the `# Decisions` header. Determinism:
    same existing file + same proposal decisions → same output."""
    existing = (
        decisions_md.read_text(encoding="utf-8") if decisions_md.is_file() else ""
    )
    if not existing.strip():
        existing = _DECISIONS_HEADER + "\n"
    new_parts: list[str] = []
    for d in sorted(decisions, key=lambda e: e.get("title", "")):
        new_parts.append("")
        new_parts.extend(_decision_entry(d))
    merged = existing.rstrip("\n") + "\n" + "\n".join(new_parts).strip("\n") + "\n"
    return merged


def _entry_label(entry: dict, fallback: str) -> str:
    """A human-readable label for a dropped entry (its title, else slug)."""
    return entry.get("title") or entry.get("slug") or entry.get("topic_slug") or fallback


def _truncate_to_cap(entries: list[dict], cap: int) -> tuple[list[dict], list[dict]]:
    """Keep the first `cap` entries (most-important-first per the prompt), drop the
    rest. Returns (kept, dropped). Deterministic: input order is preserved."""
    return entries[:cap], entries[cap:]


def _apply_caps(
    proposal: dict,
    worked_agents: set[str],
) -> tuple[dict, list[str]]:
    """Apply each per-store cap as a TRUNCATING ceiling (user decision 2026-06-01):
    write the first N (= the cap) entries for that store, DROP the excess, and
    return a log line per truncated store naming the dropped entries (Rule 2 —
    surfaced, never silent). Returns (truncated_proposal, drop_log_lines).

    Caps reuse the `_budget_check` per-store limits (single source — NOT re-defined).
    A non-worked agent's silo has an effective cap of 0, so ALL its entries are
    dropped. Truncation never raises — it is a normal bounded write (exit 0)."""
    drops: list[str] = []

    def _truncate(name: str, entries: list[dict], cap: int) -> list[dict]:
        if len(entries) <= cap:
            return entries
        kept, dropped = _truncate_to_cap(entries, cap)
        labels = ", ".join(_entry_label(e, "<untitled>") for e in dropped)
        drops.append(f"truncated {name} to {cap}; dropped: {labels}")
        return kept

    decisions = _truncate("decisions", proposal.get("decisions") or [], DECISIONS_LIMIT)
    project_topics = _truncate(
        "project_topics", proposal.get("project_topics") or [], SPEC_TOPICS_LIMIT
    )
    shared_topics = _truncate(
        "shared_topics", proposal.get("shared_topics") or [], SHARED_TOPICS_LIMIT
    )

    silos: dict[str, list[dict]] = {}
    for agent in sorted(proposal.get("silos") or {}):
        entries = (proposal.get("silos") or {}).get(agent) or []
        # Spec 047 AC-4: an UNKNOWN silo agent key is a recoverable WRITER-DROP, not
        # an exit-31 discard of the whole proposal — drop the key + WARN, keep the
        # rest. Parallel to spec 042's unresolved-`topic_slug` drop.
        if agent not in SILO_AGENTS:
            drops.append(
                f"dropped unknown silo agent key {agent!r} (not in SILO_AGENTS); "
                f"valid entries still written"
            )
            continue
        # A non-worked agent's silo cap is 0 — every entry is dropped + logged.
        cap = SILO_LIMIT if agent in worked_agents else 0
        kept = _truncate(f"silo {agent}", entries, cap)
        if kept:
            silos[agent] = kept

    truncated = {
        "decisions": decisions,
        "project_topics": project_topics,
        "shared_topics": shared_topics,
        "silos": silos,
    }
    return truncated, drops


def write_proposal(
    proposal: dict,
    *,
    canonical_dir: str | os.PathLike[str],
    repo_dir: str | os.PathLike[str],
    worked_agents: set[str] | None = None,
) -> list[str]:
    """Write a schema-valid proposal to the canonical store + repo mirror.

    The writer OWNS every path. Order: apply the per-store TRUNCATING caps (write
    the first N per store, DROP + LOG the excess — never abort), then write the
    canonical store, then mirror the non-personal `memory/` subset into the repo.
    Returns the sorted list of written paths (canonical + repo), relative to their
    store roots. Truncation is a normal bounded write (the run exits 0); the dropped
    entries are logged to stderr (Rule 2 — surfaced, never silent).

    `worked_agents` gates silo writes (AC-5: a non-worked agent's cap is 0, so all
    its entries are dropped); the canonical-vs-repo split keeps silos canonical-only
    (AC-6 — no repo-side silo path is ever constructed)."""
    worked = set(worked_agents or set())
    capped, drops = _apply_caps(proposal, worked)
    for line in drops:
        print(f"sdk_memory writer-cap: {line}", file=sys.stderr)

    canonical = Path(canonical_dir)
    written: list[str] = []

    decisions = capped["decisions"]
    project_topics = capped["project_topics"]
    shared_topics = capped["shared_topics"]
    silos = capped["silos"]

    # --- Outer canonical project memory --------------------------------------
    # MERGE, never replace (spec 038 realrun-fix): decisions.md is APPENDED; the
    # MEMORY.md index merges new lines into the existing index (preserving every
    # other line); topic bodies are overwritten ONLY for the proposed slugs.
    mem = canonical / "memory"
    topics = mem / "topics"
    outer_header = "# Memory"
    outer_index_md = mem / "MEMORY.md"
    new_outer_lines: list[str] = []

    if decisions:
        topics.mkdir(parents=True, exist_ok=True)
        decisions_md = topics / "decisions.md"
        decisions_md.write_text(_append_decisions(decisions_md, decisions), encoding="utf-8")
        written.append("memory/topics/decisions.md")
        new_outer_lines.append(
            _index_line("Decisions", "decisions", "what we decided and why")
        )

    for t in sorted(project_topics, key=lambda e: e.get("slug", "")):
        slug = t["slug"]
        topics.mkdir(parents=True, exist_ok=True)
        (topics / f"{slug}.md").write_text(
            _topic_body(t.get("title", slug), t.get("body", "")), encoding="utf-8"
        )
        written.append(f"memory/topics/{slug}.md")
        new_outer_lines.append(_index_line(t.get("title", slug), slug, t.get("hook", "")))

    if new_outer_lines or outer_index_md.is_file():
        mem.mkdir(parents=True, exist_ok=True)
        merged_outer = _merge_index(outer_index_md, outer_header, new_outer_lines)
        # Self-heal (spec 047 fix-round 2): re-index any topics/*.md left unreferenced
        # (e.g. by a prior line-drop compaction) so the orphan check never fires on a
        # reference compaction dropped. Runs on the already-merged+compacted text.
        merged_outer, healed = self_heal_index(merged_outer, topics, outer_header)
        for slug in healed:
            print(
                f"sdk_memory writer-self-heal: re-indexed orphaned topics/{slug}.md "
                f"in memory/MEMORY.md",
                file=sys.stderr,
            )
        outer_index_md.write_text(merged_outer, encoding="utf-8")
        written.append("memory/MEMORY.md")

    # --- Shared cross-agent topics (canonical-only) --------------------------
    # Each shared topic body is written, AND a merged index line is added to the
    # canonical agent-memory/MEMORY.md so the shared topic is never an orphan
    # (spec 038 realrun-fix Fix 3 — the agent-memory orphan check keys on this).
    # The silo/shared base lives UNDER the auto-memory root `memory/` (spec 047
    # AC-1 fix): `memory: project` frontmatter auto-loads from `<canonical>/memory/`,
    # so a silo at the `<canonical>/agent-memory/` sibling is never auto-loaded.
    agent_memory = agent_memory_base(canonical)
    shared_dir = agent_memory / "topics"
    shared_header = "# Agent memory"
    shared_index_md = agent_memory / "MEMORY.md"
    new_shared_lines: list[str] = []
    for t in sorted(shared_topics, key=lambda e: e.get("slug", "")):
        slug = t["slug"]
        shared_dir.mkdir(parents=True, exist_ok=True)
        (shared_dir / f"{slug}.md").write_text(
            _topic_body(t.get("title", slug), t.get("body", "")), encoding="utf-8"
        )
        written.append(f"memory/agent-memory/topics/{slug}.md")
        new_shared_lines.append(_index_line(t.get("title", slug), slug, t.get("hook", "")))

    if new_shared_lines or shared_index_md.is_file():
        agent_memory.mkdir(parents=True, exist_ok=True)
        merged_shared = _merge_index(shared_index_md, shared_header, new_shared_lines)
        merged_shared, healed_shared = self_heal_index(
            merged_shared, shared_dir, shared_header
        )
        for slug in healed_shared:
            print(
                f"sdk_memory writer-self-heal: re-indexed orphaned topics/{slug}.md "
                f"in memory/agent-memory/MEMORY.md",
                file=sys.stderr,
            )
        shared_index_md.write_text(merged_shared, encoding="utf-8")
        written.append("memory/agent-memory/MEMORY.md")

    # --- Per-agent silos (canonical-only) ------------------------------------
    # The writer constructs ONLY canonical silo paths (AC-6). There is NO repo-side
    # silo path code anywhere in this module — silos are never mirrored. The silo
    # index is MERGED into the existing per-agent index (preserving prior craft
    # entries), never regenerated from only the current proposal.
    # A silo `topic_slug` resolves iff its body exists in the shared ROOT
    # agent-memory/topics/ (shared topics for THIS proposal were already written
    # above, so the on-disk stem set already covers both pre-existing and
    # this-proposal bodies). Any dead line — new OR carried-forward — is dropped
    # at write time + logged (spec 041 AC-2; prevention complements the exit-27
    # backstop, which stays unchanged).
    resolvable_slugs = frozenset(
        p.stem for p in shared_dir.glob("*.md")
    ) if shared_dir.is_dir() else frozenset()
    for agent in sorted(silos):
        entries = silos[agent]
        agent_dir = agent_memory / agent
        print(
            f"sdk_memory writer-silo-target: {agent} -> {agent_dir}",
            file=sys.stderr,
        )
        agent_dir.mkdir(parents=True, exist_ok=True)
        silo_index_md = agent_dir / "MEMORY.md"
        new_silo_lines = [
            _index_line(e.get("title", ""), e.get("topic_slug", ""), e.get("hook", ""))
            for e in entries
        ]
        merged = _merge_index(silo_index_md, f"# {agent} memory", new_silo_lines)
        filtered, dropped = _drop_dead_silo_lines(
            merged, f"# {agent} memory", resolvable_slugs
        )
        for slug in dropped:
            print(
                f"sdk_memory writer-dead-link: dropped {agent} -> "
                f"topics/{slug}.md (target absent)",
                file=sys.stderr,
            )
        silo_index_md.write_text(filtered, encoding="utf-8")
        written.append(f"memory/agent-memory/{agent}/MEMORY.md")

    # --- Mechanical mirror: non-personal memory/ subset -> repo ---------------
    # Reuses the single-source mirror (locked to memory/, excludes personal files
    # AND index lines). Silos are structurally never reached here.
    from sdk_memory_pipeline import _mirror_canonical_to_repo

    mirrored = _mirror_canonical_to_repo(
        canonical_memory_dir=canonical,
        repo_memory_dir=Path(repo_dir) / "memory",
    )
    written.extend(f"repo:memory/{rel}" for rel in mirrored)

    return sorted(written)

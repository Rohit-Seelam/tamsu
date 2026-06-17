---
type: spike
status: draft
---

# Spec: <question>

## The question
One sentence — what we're trying to find out.

## Why we're asking
Context that motivates the investigation. What's blocked on the answer.

## Decision this informs
What we'll do differently based on the answer. If "nothing" — don't run the spike.

## Definition of "answered"
What constitutes a useful answer. Examples:

- A yes/no with one-paragraph justification
- A comparison of N options with tradeoffs
- A proof-of-concept that runs end-to-end
- A benchmark with concrete numbers

**Make this section mechanically checkable.** If the answer's shape is "5–8 dimensions, each with a name + rationale + signal of competence + depth tier from {foundational|intermediate|advanced}," the cross-checker can grep for those structural elements during verify. Vague answers like "explore the space" make the verifier helpless. The more this section reads like a schema (counts, required fields, enum-membership), the easier the spike is to verify and the harder it is for the implementer to drift. (Lesson from spike 008.)

**For externally-controlled facts** — vendor docs, language ecosystems, third-party APIs, framework versions — require URL + retrieval-date citations in the eventual `findings.md`. The cross-checker will spot-verify at least one citation via WebFetch. (Lesson from spike 010.)

**For comparison-table sections** in the answer shape — when `findings.md` must compare N options across M dimensions — require the comparison to live as a single table with one row per dimension. Prose-bullet overflow (some dimensions in the table, others as following bullets) splits the cross-checker's grep target across two locations. State an explicit row count if the comparison shape is known up front. (Lesson from spike 011: two of six required dimensions ended up as prose bullets, costing a minor finding.)

## Time box
Hours or days. If exceeded, the spike escalates to a `feature` (or is killed).

**Split heuristic:** if you find yourself spec'ing two questions whose answers each need ≥100 lines of `findings.md`, split into two spikes. Bundling produces dense findings and hard cross-cutting decisions. (Lesson from spike 010 — one rich question is fine; two interlocked rich questions strain the format.)

## Constraints
- Code written in a spike is throwaway unless explicitly promoted.
- No production code touched.
- Findings land in `findings.md` regardless of outcome (including "couldn't answer").

## Out of scope
What this spike will NOT decide or build.

## Constitution check
For each rule in `constitution.md`, mark one of: `[x]` ticked (complies), `n/a` (doesn't apply to this artifact type), or note exemption with reason. Research artifacts often legitimately mark Rule 1 (tests) and Rule 2 (no silent suppression) as `n/a` because the artifact has no behavior or error paths.

- [ ] Rule 1 — <how this complies, or `n/a` because research artifact has no behavior to test>
- [ ] Rule 2 — <how this complies, or `n/a` because no error paths>

---
name: feedback
description: Record the owner's feedback or idea about the oskiv method or plugin (a skill to add, a rule, how testing or linting should be set up, tooling) as one file in tamsu's feedback inbox. Only records; never implements. Use for /oskiv:feedback or "feedback for oskiv".
argument-hint: "<the feedback>"
---

Record this as feedback for the oskiv plugin: $ARGUMENTS (if empty, use what the owner just said
about the method).

1. **Find tamsu:** `readlink ~/.claude/CLAUDE.md` prints `<tamsu>/user/CLAUDE.md`. If it isn't a
   link, ask the owner where tamsu is.
2. **Write one file,** `<tamsu>/feedback/YYYY-MM-DD-<project>-<slug>.md`, where `<project>` is
   this repo's folder name:
   ```markdown
   # <short title>

   - **Date:** YYYY-MM-DD
   - **From:** <project>

   ## Feedback
   <the owner's words, cleaned only of dictation slips>

   ## Context
   <1–3 lines: what was happening here that prompted it>
   ```
3. **tamsu is public.** Keep out secrets, keys, personal data, absolute home paths, and this
   project's private content (code, data, names). Describe the pattern, not the data. If the
   feedback can't be stated without them, ask.
4. **Only record.** Change nothing else, don't commit (tamsu sessions commit the inbox), and
   don't start implementing it. Reply with the file path in one line.

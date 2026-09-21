---
name: orient
description: Session-start ritual for this repo (WP-24.G). Prints the status board with ages, the open inbox oldest first, the record audit (contradictions, ADR revisit conditions) and the owner's competence gate when a promotion is pending. Run at turn 1 of any session in Macro-Assist, before proposing or starting work.
allowed-tools: Bash(python .macro-assist/orient.py:*)
---

Run, from the repo root:

```bash
python .macro-assist/orient.py
```

Show its output to the user in full, in one code block — it is the session's
starting state, not something to summarise away. It never writes.

Then, in a few lines, say what the output changes about the session:

- **A `RED` line in AUDIT** is a failing CI check. Say so first. Never
  resolve a `contradictions` red by picking a side: on *status* the board
  (`docs/record/active-experiments.md`) wins and the other sources get
  fixed; on *substance* the detailed doc wins and the board row gets fixed
  (`CLAUDE.md` → Orientation). A pin (`KNOWN_CONTRADICTIONS`,
  `KNOWN_ITEM_COLLISIONS`, …) is only for a disagreement that is deliberate
  and carried by an open `todo.md` item.
- **An ADR REVISIT line** means a decision's stated revisit condition may
  have come true. Read that ADR before touching what it decided; whoever
  re-reads it edits the section — even to say "and it did not fire" — which
  clears the line.
- **A COMPETENCE GATE block** means the hypothesis register holds entries
  the owner has not yet rewritten. You may run looks, pull artifacts and
  draft register entries; you do **not** write the pre-registration text of
  a promoted hypothesis, and you do not read the sealed slice for one
  (how-we-explore §6, convention #7).
- **The BOARD's `next:` lines** are what each track is waiting on. They are
  not instructions — ask what the session is for.

If the script fails, say why (a shallow clone or a checkout without git
history makes the ages unreadable — `record_audit.py` is red there for the
same reason) and fall back to reading `CLAUDE.md` and the board directly.

Details: `docs/reference/operations.md` → *Record audit*.

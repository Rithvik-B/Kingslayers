# Decision log

One file per decision, so teammates working at the same time never edit the same file.

## Rules

- **File name:** `YYYY-MM-DD-HHMM-short-slug.md`, local time, from `date +%Y-%m-%d-%H%M`. Names sort in
  order and don't collide.
- **Status:**
  - `proposed`: suggested, waiting for the team to agree
  - `accepted`: the team agreed; every Claude follows it
  - `superseded by <file>`: replaced by a newer decision
- **Don't rewrite accepted decisions.** To change one, write a new decision and set the old one's status to
  `superseded by <new file>`. Typos and added links are fine.
- **Keep it short.** A few lines per section is enough during a hackathon. Reasons matter more than length.
- Push right away (`/decide` does this) so other teammates' Claudes see the decision on their next session or
  `/sync`.

## Template

```markdown
---
title: <one line: what we decided>
status: proposed | accepted | superseded by <file>
date: YYYY-MM-DD
decided_by: <names>
---

## Context
What problem or question made this necessary.

## Decision
What we will do. Be specific enough that someone who missed the conversation can act on it.

## Why
The main reasons, and what we gave up.

## Alternatives considered
- <option>: why not

## Consequences
What this changes for the team: files, owners, next steps, things we now can't do.
```

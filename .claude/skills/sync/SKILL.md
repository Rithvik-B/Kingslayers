---
name: sync
description: Pull the latest from origin and summarize what teammates changed (decisions, status, ideas, notes, code). Use when the user runs /sync, at the start of a work session, or when the session-start hook reports the branch is behind origin.
---

Bring this checkout up to date and tell the user what changed.

1. Run `git status --short` and `git fetch origin`. Save the upstream position before pulling:
   `before=$(git rev-parse @{u})`.
2. Run `git pull --rebase --autostash`. If a conflict shows up, stop and show the user the conflicting files.
   Don't resolve conflicts in code someone else owns.
3. Look at what came in, using `git log --format='%h %an %ar %s' $before..@{u}` and
   `git diff --stat $before..@{u}`. If nothing came in, say "Already up to date" and summarize
   `docs/STATUS.md` in two lines.
4. Read everything that changed under `docs/`, plus `CLAUDE.md` if it changed. Then give a short summary:
   - **New or changed decisions:** title, status and one line on what it means for this user's work
   - **Status changes:** phase, owners, next steps, blockers
   - **New ideas or notes:** one line each
   - **Code:** which areas changed and who changed them
   - **Heads-up:** anything that conflicts with what this user is doing or planned in this session
5. If `CLAUDE.md` or `docs/STATUS.md` changed, re-read them now. The copy loaded at session start is out of
   date.

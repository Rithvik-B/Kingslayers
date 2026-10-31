---
name: handoff
description: Save this session's progress for the team. Updates docs/STATUS.md, records any unrecorded decisions, saves lessons to docs/notes, then commits and pushes. Use when the user runs /handoff, is wrapping up, or is switching tasks.
---

Leave the repo so that a teammate's Claude can pick up from here with no chat history.

1. **Sync first.** Run `git pull --rebase --autostash`. That way you edit the latest STATUS.md.
2. **Decisions.** Look back over this session for anything settled that has no file in `docs/decisions/`.
   List those items for the user, and record the ones they confirm, following the `/decide` steps.
   Combine them into this handoff's commit instead of pushing each one separately.
3. **Notes.** Save anything a teammate would otherwise rediscover the hard way, such as Crustdata API quirks,
   credit costs, endpoints or filters that worked, dead ends, or setup steps. Put it in
   `docs/notes/<topic>.md`, adding to the file if it exists.
4. **Status.** Update `docs/STATUS.md`:
   - this user's row in **Team**: what they own and are working on now
   - **Next steps**: tick off what's done and add what comes next, with an owner where known
   - **Open questions** and **Blockers**
   - the "Last updated" line, with the date and name
5. **Commit and push.**
   - Doc changes: stage only the files edited above. Commit them as `handoff: <one-line summary>`.
   - Code changes: show `git status --short` and ask whether to commit them as well, and with what message.
     Never commit `.env` or anything that looks like a secret.
   - Then run `git pull --rebase --autostash` and `git push`. Never force-push.
6. Reply to the user in three lines: what was saved, what's next, and anything a teammate is now waiting on.

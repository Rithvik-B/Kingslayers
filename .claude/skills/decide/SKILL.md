---
name: decide
description: Record a team decision in docs/decisions/ and push it so every teammate's Claude sees it. Use when the user runs /decide, or says the team settled something (the idea, scope, stack, an API, the data model, who owns what, the demo plan, a cut feature).
argument-hint: <what was decided>
---

Record this decision for the team: $ARGUMENTS

1. **Check for overlap.** List `docs/decisions/` and read any decision on the same topic.
   - If the new decision replaces an existing one, set the old file's `status:` to
     `superseded by <new-file-name>`. Leave the rest of the old file unchanged.
   - If it conflicts with an accepted decision and the user didn't say it replaces it, stop and ask.
2. **Fill in what's missing.** You need the decision itself, the reason, and who decided. Take what you can
   from the conversation. Ask the user only for what is still missing, and ask in one question. Use status
   `accepted` when the team agreed, or `proposed` when it is one person's suggestion that still needs
   agreement.
3. **Write the file** at `docs/decisions/$(date +%Y-%m-%d-%H%M)-<short-slug>.md`. Use the template in
   `docs/decisions/README.md` and keep each section to a few lines.
4. **Update `docs/STATUS.md`** if the decision changes the phase, next steps, owners or open questions.
   Update the "Last updated" line too.
5. **Publish it now.** The team agreed that doc changes are pushed right away (see the first decision in
   `docs/decisions/`). Stage only the files you wrote or edited above. Never sweep in other uncommitted work.
   ```
   git add docs/decisions/<file> [docs/decisions/<superseded file>] [docs/STATUS.md]
   git commit -m "decision: <title>"
   git pull --rebase --autostash
   git push
   ```
   If the rebase conflicts, resolve it when the conflict is only in docs and both sides' content can be
   kept. Otherwise stop and show the user. Never force-push.
6. Reply with one line: the decision's title, its status and the file path.

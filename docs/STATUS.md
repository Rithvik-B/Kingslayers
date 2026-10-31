# Status board

_Last updated: 2026-10-31 14:25 by Rithvik (PLAN.md written; build starting)_

## Phase

**Build.** Code freeze at **15:10 IST today**. The contract is `PLAN.md` at the repo root, and it wins over
every other doc.

**Idea:** a sales agent with "every claim has a receipt". It finds real companies through live Crustdata,
writes an email where every claim cites its source, reads the reply, and books a real Calendar meeting with
a Meet link. The demo runs in STAND_IN mode: real data, but the one email goes to the stand-in inbox.

## Event

- ContextCon 03, IIT Bombay, by Crustdata. Freeze at 15:10 today, then a 3-minute live demo plus Q&A.
- **Demo laptop:** Rithvik's, logged in to Claude Code as him. See `docs/decisions/`.

## Team (only the owner edits a file; ownership is in `PLAN.md` §3)

| Role | Name | Owns | Doing now |
|---|---|---|---|
| P1 | Rithvik | app shell, models, routes, UI, README, demo | skeleton push by 14:15 |
| P2 | _(fill in)_ | llm, crustdata, scoring, discovery, drafting | Crustdata field-name check by 14:15 |
| P3 | _(fill in)_ | gates, mail, calendar, outreach, inbox, booking | Composio check (send, thread, slots, Meet link) by 14:15 |

## Next steps

- [ ] 14:15: P1 pushes the skeleton. P2 pushes `docs/notes/crustdata-rest.md`. P3 pushes
      `docs/notes/composio-tools.md`.
- [ ] 14:40: Tier 1 pushed by everyone.
- [ ] 14:40–14:55: integration run on Rithvik's laptop; owners fix their own files.
- [ ] 14:55–15:05: pre-run discovery (limit 20), reset rehearsal data, rehearse `PLAN.md` §10.
- [ ] 15:05–15:10: README, final push, submit.

## Open questions

- Does Composio's `CREATE_EVENT` return a Meet link for our seller account? P3 checks at 14:15. Fallback in
  `PLAN.md` §6.8.
- What are the real business-email status values in Crustdata? P2 checks at 14:15 and sets
  `ACCEPTED_EMAIL_STATUSES`.

## Blockers

None.

# Status board

_Last updated: 2026-10-31 14:22 by Rithvik (role cards and Seller Memory added to PLAN.md)_

## Phase

**Build.** Code freeze at **15:10 IST today**. The contract is `PLAN.md` at the repo root, and it wins over
every other doc.

**How to start:** open Claude Code in the repo and type `@PLAN.md I am P1` (or P2, or P3).

**Idea:** a sales agent with "every claim has a receipt", and a **Seller Memory** where the seller sees and
edits everything the agent believes and decided (product, ICP and GTM, voice, rules, decisions). It finds real companies through live Crustdata,
writes an email where every claim cites its source, reads the reply, and books a real Calendar meeting with
a Meet link. The demo runs in STAND_IN mode: real data, but the one email goes to the stand-in inbox.

## Event

- ContextCon 03, IIT Bombay, by Crustdata. Freeze at 15:10 today, then a 3-minute live demo plus Q&A.
- **Demo laptop:** Rithvik's, logged in to Claude Code as him. See `docs/decisions/`.

## Team (only the owner edits a file; ownership is in `PLAN.md` §3)

| Role | Name | Owns | Doing now |
|---|---|---|---|
| P1 | Rithvik | app shell, models, memory, routes, UI, README, demo | foundation push by 14:30 |
| P2 | Dinesh | llm, crustdata, scoring, discovery, drafting | all P2 modules written and unit-tested; REST self-check waits on `.env` |
| P3 | _(fill in)_ | gates, mail, calendar, outreach, inbox, booking | Composio check (send, thread, slots, Meet link) by 14:30 |

## Next steps

- [ ] By 14:30: P1 pushes the foundation (models, db, config, journal, memory). P2 pushes
      `docs/notes/crustdata-rest.md` and `llm.py`. P3 pushes `docs/notes/composio-tools.md`, including the
      Meet-link result.
- [ ] 14:50: Tier 1 pushed by everyone, and everyone reports to their user.
- [ ] 14:50–15:08: integration on Rithvik's laptop; owners fix their own files.
- [ ] 15:08–15:10: README, final push, **code freeze**.
- [ ] After the freeze: pre-run discovery (limit 20), reset rehearsal data, rehearse `PLAN.md` §10.

## Open questions

- Does Composio's `CREATE_EVENT` return a Meet link for our seller account? P3 checks by 14:30. Fallback in
  `PLAN.md` §6.8.
- ~~What are the real business-email status values in Crustdata?~~ **Answered (P2):** `deliverable`, `catch_all`,
  `invalid`, `unknown`. Set `ACCEPTED_EMAIL_STATUSES=deliverable,catch_all` in `.env` and `.env.example`
  (the `verified,valid` default matches nothing). Details: `docs/notes/crustdata-rest.md`.

## Blockers

None.

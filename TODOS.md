# TODOS: deferred, do NOT build today

These are Tier 3 items from `PLAN.md` §11. They're kept for the pitch ("what comes next") and for after the
hackathon.

- **A structured form editor for the ICP.** Today the ICP is edited as JSON in the Seller Memory panel. Next:
  a form for each criterion's field, type and weight. Only supported fields can be mandatory.
- **More Seller Memory:** campaign-level overrides in the UI, a memory diff view, and letting the agent
  learn rules from the seller's edits.
- **Follow-ups and the demo clock.** Up to 2 follow-ups at day 3 and day 7, then `EXHAUSTED`, with a
  "Fast-forward 3 days" control.
- **REPLAY.** Cache Crustdata responses in `data/replay/` and add a manual REPLAY toggle and badge.
- **URL intake.** Read the product from its website, with SSRF protection.
- **After BOOKED:** Meet transcripts (needs a paid Google Workspace organizer), a Meeting Prep brief, and
  the follow-up email.
- **Slack alerts** for NEEDS_HUMAN and BOOKED, through Composio.
- **Warm intros and social connections**, labelled "likely knows" and never claimed as a real connection.
- **Backtest on past data.** Pick companies as of a past date and check which later hired for the role or
  bought something in the category. This matches the Revenue theme's "more every run".
- **Funding and new-leader "why now" signals**, via `company_enrich` funding fields and recent hires.
- **Production hardening.** Postgres, a job queue, per-tenant auth, and an Anthropic Console API key
  instead of a Max login (required once anyone other than us uses the app).

> **REFERENCE ONLY. `PLAN.md` at the repo root is the build contract and wins on every conflict.**
> Superseded here: direct Google OAuth, SMTP/IMAP/.ics fallback, Next.js frontend, "pick any LLM provider", the 5-hour timeline, the `~/.gstack` and `/home/...` paths. ICP editing is no longer deferred: the ICP, product, voice and rules are editable in Seller Memory (`PLAN.md` §6.13).
> Still valid where PLAN.md cites it: the claim gate, send gates, recipient guard, contact states, inbox matching, and the BOOKED rule.

# Build Spec: ContextCon Sales Agent (5-hour hackathon build)

Status: APPROVED design, ready to build. This file is the implementation contract.
Where it conflicts with `ContextCon_Sales_Agent_Claude_Code_Spec.md` (the original long spec), THIS file wins.
The original spec is reference material for formulas and contracts this file cites by section (§6.3, §8.4, §9.2, §9.5, §11).

Supporting files:
- `docs/CRUSTDATA_ENDPOINTS.md`: which Crustdata endpoints are enabled on the tested key
- `docs/assets/wireframe-campaign.png` (+ `.html`): approved layout of the main campaign screen
- `TODOS.md`: deferred work, do not build

## Problem Statement

A seller gives the agent a product. The agent finds real companies that should buy it (live Crustdata), picks the right person at each, writes an email whose factual claims about the prospect each link to a source, handles the reply, and books a real calendar meeting with a Google Meet link.

"Booked" means a Google Calendar event exists with a valid slot and a Meet link, plus the right attendees. The right attendees are the seller as organizer and the delivered recipient: the stand-in in STAND_IN mode, the real prospect in LIVE mode. A sent email, a positive reply or an emailed `.ics` file is not a booking (spec §1.1).

The deliverable is a working product, not a mock: given the seller's input, it can book meetings with real prospects once LIVE mode is switched on. [user: "overall goal is a final deliverable which actually schedules meets with prospects after taking input from user (a product as close as it can in a 5 hour hackathon)"] It gets built in a 5-hour hackathon and shown as a 3-minute live demo in STAND_IN mode, plus 2 minutes of Q&A. Past ContextCon events ran 5 hours (April, Crustdata + YC; source: https://crustdata.com/contextcon) and about 9 hours (October 24, "Agentic Services Hackathon", judged partly by a "demo they'd hire" vote; source: https://luma.com/4xdm1jm8). [fetched 2026-10-31]

## What Makes This Cool

- **Every claim about the prospect has a receipt.** Each company pick, score, "why now" signal and factual sentence about the prospect in an email links to the Crustdata record behind it. A judge can click any `[src]` and see the raw record. Positioning hypothesis: vendor write-ups in 2026 blame stale data and surface-level personalization for many AI SDR failures (https://www.apollo.io/insights/what-are-the-limitations-of-current-ai-sdr-tools, https://www.kwanzoo.com/blog/why-first-gen-ai-sdrs-failed). This demo aims at the opposite. Limits of the guarantee are listed under Claim gate.
- **The booking happens live, on stage.** The judge (or a teammate) is the stand-in prospect. They get the email, reply from their phone, pick a slot, and a Google Calendar invite with a Meet link lands in their calendar during the 3 minutes.

## Constraints

- **Clock:** 5 hours of build, then code freeze. The demo is 3 minutes. [user message after D8; narrows D4's 5-9 hours]
- **Crustdata (personal account, read 2026-10-31 via MCP list_tools):** about 15,160 credits. On plan: `company_search` (including natural-language `search`), `person_search`, `person_enrich` (business email via `contact.business_emails`, 15 rpm; `/person/contact/enrich` is DISABLED on this key, see `docs/notes/crustdata-endpoints.md`), `job_search` (~0.03 cr/result), `company_enrich`, `web_enrich_live`. Not on plan: every `batch_*` endpoint. The hackathon-issued key may differ, so re-check it at kickoff. [measured: Crustdata MCP account summary]
- **Estimated live-run cost** [estimated from the plan's per-result prices], about 100 credits per full run:

  | Call | Volume | Cost |
  |---|---|---|
  | `company_search` | ~60 results × (0.03 base + 0.2 headcount group) | ~14 cr |
  | `job_search` | ~40 companies × ~10 postings × 0.03 | ~12 cr |
  | `person_search` | 20 companies × ~5 people × ~0.13 | ~13 cr |
  | `person_enrich` (business email add-on) | ~40 contacts × ~2 (1 base + 1 email) | ~80 cr |

  A pre-run plus 2 rehearsals is about 300 cr, which fits the ~15,160 balance. Per-run ceiling: 150 cr, tracked from `credits_used`. Discovery stops and shows a warning when the ceiling is reached.
- **Outbound safety:** in the default STAND_IN mode, no email or calendar invite reaches a real prospect. All delivery goes to one stand-in address, enforced in code. LIVE mode, which sends to real verified prospects, exists only behind an env flag plus per-campaign consent, and is never used on stage. (See Delivery modes and Safety rules.) [user answers: premise 3, D9]
- **Google OAuth:** app in testing mode. Only the seller account (the one that grants Gmail and Calendar access) is a test user; the stand-in is just a recipient. Consent shows an "unverified app" screen, which is fine for a demo. Testing-mode refresh tokens expire after about 7 days, so re-authorize within 7 days of the demo.
- **LLM:** keys for all major providers are available. Use one provider, behind a narrow adapter (spec §3.1).
- **Weekend/evening demo:** today, 2026-10-31, is a Saturday, and demos run late in the day. The demo can't depend on real business hours (see Time rules).

## Premises (agreed)

1. **A demo, not a platform.** Cut Docker Compose, Postgres plus Alembic, APScheduler plus a worker process, JWT/tenants, and most of the 21 spec tests. Keep the spec's best ideas as small deterministic code: evidence-aware scoring (§6.3), send gates (§8.2, §8.4), the reply table (§9.2, trimmed) and the definition of "booked" (§9.5).
2. **Live Crustdata is the default.** The REPLAY fallback (defined below) is built only if time allows. Without it, the pre-run's stored results in SQLite are what the stage shows.
3. **Real discovery, one stand-in prospect.** Crustdata finds real companies, people and work emails. Every send is delivered to one stand-in address (the judge's or the builder's). A human replies by hand from that inbox, and the agent classifies the reply and acts.
   - Automated actions in this build: suppress, offer slots, book. Follow-ups are a stretch item.
   - QUESTION, OBJECTION, LATER, OUT_OF_OFFICE, REFERRAL and UNCERTAIN go to a NEEDS_HUMAN hold shown in the journal.
   - [user: "let it find the real emails but we send the email to one fake prospect which is the judge's or my own email and write responses and the followups come accordingly"]
4. **The wedge is "every claim has a receipt."**
5. **The demo ends at a real calendar invite,** not at "email sent."
6. **Deliver 1, hold the rest (STAND_IN mode).** Only the featured prospect's email reaches the stand-in inbox. The other drafts are fully generated, pass the send gates, and are put in the HELD state. [user answer D7]
7. **LIVE switch, stand-in default.** The same pipeline can deliver to real verified prospects when a seller turns on LIVE mode and gives explicit consent. STAND_IN stays the default and the stage mode. [user answer D9]

Note: the user explicitly confirmed 3, 6 and 7. Premises 1, 2, 4 and 5 were presented and not objected to.

## Approaches Considered

- **A) Thin live loop:** one Python process, Gmail SMTP/IMAP with an app password, `.ics` invite. Not chosen: the user wants real free/busy, a real Meet link and the spec's architecture.
- **B) Spec-faithful Google stack:** CHOSEN, details below.
- **C) Visible agent loop:** the LLM picks its own tool path. Not chosen because it can behave differently on stage than in rehearsal. Its live journal panel is kept in B's UI (see wireframe).

## Recommended Approach: B, spec-faithful Google stack (trimmed)

**Stack:** Next.js (App Router, TypeScript, Tailwind) for the UI. FastAPI plus Pydantic v2 for the API. SQLite via SQLAlchemy; `create_all` is acceptable for a one-day demo. One backend process runs an asyncio background loop for inbox polling and due actions. No separate worker, no APScheduler.

**Provider interfaces (spec §11, trimmed):** `CompanyDataProvider` (Crustdata live; replay only if time allows), `MailProvider` (Gmail API), `CalendarProvider` (Google Calendar API), `LLMService`, and an injectable `Clock` (real time; the fast-forward offset only if the follow-up stretch gets built).

**Pipeline:**

```
product text (URL intake cut for the demo)
  -> LLM: ProductProfile + ICP (user approves or regenerates; editing is deferred, see TODOS.md)
  -> Crustdata company_search (NL query + country/headcount filters)
  -> job_search per company (hiring signals = buying readiness)
  -> deterministic scoring §6.3 (fit, coverage, tier) -> top 20
  -> person_search for TA/HR roles -> role labels (CHAMPION / ECONOMIC_BUYER)
  -> /person/enrich fields [contact.business_emails] (15 rpm) for top 1-2 per company; use /person/contact/enrich only if the event key enables it
  -> LLM draft: sentences typed + evidence_ids per prospect claim
  -> claim gate + send gates
  -> seller clicks Send: Gmail send to delivered recipient (STAND_IN: stand-in; LIVE: verified email); others: HELD
  -> inbox poll on thread (15s) + "Check inbox now" button, one shared lock
  -> strip quoted text, deterministic opt-out override, then LLM classify (§9.3)
  -> INTERESTED: free/busy next 7 business days -> offer 3 numbered slots in the same thread
  -> recipient picks -> recheck free/busy -> events.insert
       (event id from meeting row, attendees=[delivered recipient], conferenceDataVersion=1, sendUpdates=all)
  -> BOOKED only after event id + Meet link come back
```

### Stage plan and latency budget

Discovery is too slow to run inside 3 minutes: LLM ICP, company_search, about 20 job_search calls, people search, contact enrich and about 40 LLM drafts. The plan:

- **Pre-run before going on stage.** Discovery, scoring, people, enrich and all drafts run 10-20 minutes before the demo on live data. The UI shows "Discovery ran at HH:MM on live Crustdata."
- **Live on stage, in order:**
  1. Show the ranked table and click two receipts (~40s).
  2. Open the featured prospect's draft with its receipts (~20s).
  3. Click Send (~5s).
  4. The stand-in replies "interested" from their phone. Click "Check inbox now" (~30s).
  5. Slots arrive. The stand-in replies "2" (~30s).
  6. "Check inbox now" books, and the invite with the Meet link appears on the stand-in's phone (~20s).
- **Budget:** about 2.5 minutes, with about 30 seconds of slack.
- **Speed:** during the pre-run, Crustdata calls within a stage run in parallel (`asyncio.gather`), and drafts generate in parallel.

### Featured prospect

The seller stars one contact in the prospect table. The default is the top-ranked Tier 1 contact whose draft passes all gates. Because discovery is pre-run, the featured contact can't change between pre-run and stage. If the rehearsed company drops out of a fresh pre-run, use the new default and re-rehearse once.

### Receipts

Each evidence row stores the Crustdata endpoint, field path, observed value, `retrieved_at`, and a raw JSON excerpt. If the record carries a source URL (a job posting URL or profile URL), that is stored too; no URL is ever invented.

Clicking `[src]` opens an in-app evidence drawer showing those values. Receipts appear in the UI only, never in the delivered email.

### Claim gate

The LLM returns the draft as a list of sentences, each typed as `prospect_fact`, `product_fact`, `hypothesis`, `cta` or `opt_out`.

- Every `prospect_fact` must carry at least 1 `evidence_id` that exists for that company or contact. Otherwise the sentence is dropped.
- If dropping it leaves fewer than one `prospect_fact`, the draft is blocked and shows "needs review."
- Each `product_fact` must carry a `profile_field` key naming a field in the approved ProductProfile (e.g. `capabilities[2]`, `value_proposition`). The gate checks that the key exists in the approved profile. If it doesn't, the sentence is dropped. A draft with zero `product_fact` sentences is still sendable, as long as it keeps at least one `prospect_fact`, the CTA and the opt-out line.
- Hypotheses are worded as questions or "might," and that is checked by prompt only.
- **The opt-out line is fixed text appended in code,** not generated by the LLM. In LIVE mode it includes the sender's identity and postal address from the consent record. If the LLM leaves out a `cta` sentence, the draft is blocked as "needs review."
- **Draft review UI:** each sentence shows its type. `prospect_fact` sentences show the cited evidence value beside them, and `product_fact` sentences show the cited profile field's value, so the seller can compare before clicking Send.
- **Accepted residual risk:** the gate checks that citations exist, not that they support the sentence. Sentence types are self-reported by the LLM, so an uncited claim mislabeled as a hypothesis passes. The seller's review before each Send is the backstop. "Every claim has a receipt" means every typed fact is cited, not that every citation was verified by a machine.

### Send gates

Every external action checks these immediately before the provider call: initial send, follow-up, slot offer and calendar insert.

- Campaign is active (not paused).
- The contact's real email comes from Crustdata (`contact.business_emails`) and its `status` is in the accepted set (decide at 0:00 after seeing real status values; default accept only the strongest value, e.g. `verified`/`valid`).
- The contact isn't suppressed and is in a sendable state.
- Per-contact attempt caps: 1 initial + max 2 follow-ups.
- Send cap: 1 delivered contact in STAND_IN mode; the consented max in LIVE mode.
- Time rules (below).

Pause blocks all of these, including slot offers and bookings, per spec §1.4.

### Delivery modes

Each campaign has a `delivery_mode`: `STAND_IN` (the default) or `LIVE`.

| | STAND_IN (default, stage) | LIVE (real prospects) |
|---|---|---|
| Recipient and attendee | `STAND_IN_EMAIL` only | the contact's Crustdata-verified business email |
| Enabled when | always | env `OUTBOUND_ENABLED=true` AND the campaign's consent record exists |
| Consent record | n/a | seller ticks "I authorize sending to real prospects," confirms sender account, sender name and company, postal address (for the footer), max sends (default 5 per campaign; 10 initial sends/day hard ceiling), follow-up cap and end date; saved with timestamp. Compliance with local email law is the seller's responsibility, and the form says so. |
| Prospect scope | any | only contacts whose company country matches the seller's (India for the MVP), so IST slots and send hours fit |
| Send cap | 1 delivered contact (rest HELD) | the consented max sends |
| Send-hours gate | demo window: any time | strict Mon-Fri 09:00-18:00 in the seller timezone (Asia/Kolkata) |
| UI | badge "STAND-IN: sends go to judge@…" | red badge "LIVE: real prospects" on every screen |

- **LIVE send trigger:** nothing sends automatically. The seller reviews each draft and clicks Send on it, and drafts are listed in rank order. Once the consented max is reached, the remaining drafts move to HELD and their Send buttons are disabled. A LIVE draft with no Send click is never delivered by any loop. (Transition READY -> CONTACTED in LIVE requires a `send_approved_at` timestamp on the message.) STAND_IN works the same way, with one Send click for the featured contact.
- **After the initial Send, these happen automatically for that contact,** within the guard: reply handling, suppression, slot offers and the calendar booking, since the seller's Send click plus consent authorizes the conversation. Follow-ups (if built) are also automatic within the consented follow-up cap. Anything in NEEDS_HUMAN waits for the seller.
- Mode is set at campaign creation and can't be changed on a running campaign. Switching means creating a new campaign, so a stage campaign can never flip to LIVE.
- Pause stops both modes.
- `DEMO_MODE=true` in `.env` (the stage laptop) refuses to create LIVE campaigns at all.

### Safety rules (enforced in code)

- **Recipient guard inside the providers.** `MailProvider.send` and `CalendarProvider.create_meeting`, including any fallback implementations, receive the campaign's mode and check the recipient or attendee right before the API call:
  - In STAND_IN, anything other than `STAND_IN_EMAIL` raises an error (fail closed).
  - In LIVE, the guard re-checks all of the following before every provider call (send, follow-up, slot offer, calendar insert), and raises an error if any fails:
    - `OUTBOUND_ENABLED=true` in the env at call time; this is the global kill switch.
    - `DEMO_MODE` is not true.
    - The campaign has a consent record, is active, and the consent end date hasn't passed.
    - Send caps apply only to the initial send to a contact not yet delivered on this campaign. Two limits apply: distinct delivered contacts on the campaign must be below the consented max (a per-campaign total), and initial sends today must be below 10 (the per-day hard ceiling). For follow-ups, slot offers and calendar inserts, the guard checks instead that the contact is already counted as delivered on this campaign. Unit test: with max=1 and one delivered contact, a slot offer and an insert for that contact succeed, and an initial send to a second contact is rejected.
    - The recipient equals that contact's `verified_email`.
    - A unit test asserts that flipping `OUTBOUND_ENABLED` to false blocks a send on an existing consented LIVE campaign.
  - Unit tests cover both modes. One asserts that a real address is rejected in STAND_IN; another asserts that an unconsented LIVE campaign is rejected.
- **Suppression is keyed to the logical contact,** meaning the real prospect's normalized email or contact id. It is never keyed to the stand-in address. It applies across all campaigns in both modes, and an opt-out from a LIVE prospect is permanent.
- **Every LIVE email includes an opt-out line.** A reply of "remove me" or "unsubscribe" suppresses the contact through the deterministic override. `make reset-demo` (or `POST /demo/reset`) runs between rehearsals and the live run. It deletes STAND_IN campaigns, their contacts' message, meeting and processed-message rows, and suppression rows created by STAND_IN campaigns. It never touches LIVE campaigns or any suppression row created from a LIVE campaign. A unit test asserts that a LIVE opt-out survives `reset-demo`.
- **No secrets or real people's data in the repo.** SQLite DB, replay cache and OAuth token file live in `data/`, which is in `.gitignore`. Only `.env.example` is committed. No fixture containing real people is committed.

### Contact states (trimmed from spec §9.1)

```
READY -> CONTACTED -> WAITING
WAITING -> FOLLOWUP_DUE -> WAITING            (follow-up sent)
WAITING -> EXHAUSTED                          (2 follow-ups, no reply)
WAITING -> REPLIED
REPLIED -> SCHEDULING                         (INTERESTED / MEETING_REQUEST)
REPLIED -> SUPPRESSED                         (NOT_INTERESTED / OPT_OUT / BOUNCE)
REPLIED -> NEEDS_HUMAN                        (everything else, low confidence, or empty new text)
REPLIED -> SCHEDULING                         (reply proposes a time: confirmation offer sent)
WAITING | FOLLOWUP_DUE -> SUPPRESSED          (opt-out found elsewhere, bounce, or seller Suppress)
SCHEDULING -> SCHEDULING                      (conflict on recheck: re-offer 3 new slots)
SCHEDULING -> NEEDS_HUMAN                     (slot reply unparseable)
SCHEDULING -> SUPPRESSED                      (opt-out / not interested during scheduling)
SCHEDULING -> BOOKED                          (event id + Meet link returned)
SCHEDULING -> MEETING_READY_TO_BOOK           (insert failed or no Meet link; user task)
NEEDS_HUMAN -> SCHEDULING                     (seller clicks "Treat as interested": slot offer sent through gates)
NEEDS_HUMAN -> SUPPRESSED                     (seller clicks "Suppress")
NEEDS_HUMAN -> WAITING                        (seller clicks "Dismiss")
READY -> HELD                                 (draft passed gates but over send cap)
```

- **NEEDS_HUMAN shows the new reply text and the raw body,** with three buttons: "Treat as interested," "Suppress" and "Dismiss." Every resulting action runs through the same send gates. On stage, this is the recovery if a reply is misread.

- **HELD is terminal for the campaign.** No loop, fast-forward, retry or follow-up can send a HELD draft. Held drafts don't count toward send caps. The funnel shows them as "Drafted (held)," and the wireframe's Emailed count becomes "Emailed 1 · Drafted 12 (11 held)."
- **Dropped from spec §9.1:** PAUSED and its LATER/OOO resume transitions (they become NEEDS_HUMAN), and INTRO_PENDING.

### Inbox matching and idempotency

- **Matching an inbound message to a contact** requires both:
  - the message is in a known Gmail thread (`threadId`, which also carries `In-Reply-To`/`References`);
  - its `From` address is the contact's delivered recipient: `STAND_IN_EMAIL` in STAND_IN mode, the contact's verified email in LIVE mode.
- **Messages the inbox pass skips or holds:**
  - From the seller account or labeled `SENT` (the agent's own initial email, slot offer and confirmations): skipped.
  - From any other sender in a known thread: go to the "Unmatched" journal for a human.
  - In no known thread: also go to "Unmatched." They are never attached to a guessed contact.
  - An Unmatched item has an "Attach to contact" action. The seller picks the contact, and the message then runs the normal opt-out override, classification and send gates. It also has "Dismiss."
- **Every follow-on email stays in the contact's original thread:** slot offers, confirmations and follow-ups are sent with the stored `threadId` plus `In-Reply-To`/`References`. The thread id from the initial send is stored as the contact's known thread.
- **Only new reply text gets read.** Before the opt-out override, the slot parser and classification run, the message is cut down to its new text. That strips quoted history (`On … wrote:` blocks and lines starting with `>`), Gmail's quoted-text div, and signatures after `-- `. The raw body is kept for the audit log. Unit tests:
  - An "interested" reply that quotes the opt-out line is not suppressed.
  - A "2" reply that quotes the numbered slot list parses as slot 2.
  - If the new text is empty after stripping (a forward, an odd quoting style, an attachment-only reply), the message goes to NEEDS_HUMAN with the raw body shown, and is never classified.
- The background poll and "Check inbox now" share one `asyncio.Lock`, so only one inbox pass runs at a time.
- A `processed_messages` table, unique on the Gmail message id, makes each inbound message classify and act exactly once.
- Outbound messages carry a unique `idempotency_key`: contact + step + attempt number (e.g. `c42:slot_offer:2` for a re-offer after a conflict).
  - A send records a `PENDING` row before the API call and won't repeat for the same key.
  - On a provider error with a clear failure (4xx, or a 5xx before any response), the row is marked `FAILED`, shown in the journal, and can be retried with a new attempt number.
  - On a timeout or other unclear result, the row is marked `UNKNOWN`. The code searches the thread for the message before any retry, and never re-sends automatically.
- `events.insert` uses an event id derived from the `meetings` row UUID. The row is created when the stand-in or prospect picks a slot, and it is new for every booking attempt; a retry of the same attempt reuses it. Contact ids use UUIDs, so ids can't be reused after a reset.
- Before inserting, the code calls `events.get` on that id:
  - Found with `status != cancelled`: treat it as already booked and read the Meet link from it.
  - Found as `cancelled`: treat it as not booked, create a new meeting row (new id) and insert.
  - A 409 from insert: run `events.get` again and apply the same rule. Never mark BOOKED without a non-cancelled event.

### Slot offer and booking

- **The offer email** lists 3 numbered slots, 20 minutes each, on the next 7 business days. Slots fall inside the seller's 09:00-18:00 Asia/Kolkata working hours with 10-minute buffers, and each is shown with date, time and "IST." The email says "Reply with 1, 2 or 3."
- **Parsing the reply:** a deterministic parser accepts `1|2|3`, "option 2" and "#2". If that fails, the LLM tries to map the reply to one of the offered slots. If that also fails, the contact goes to NEEDS_HUMAN.
- **If the first reply already proposes a time:** parse it with the LLM. If it is in the future, inside working hours and free, send a confirmation that offers that time as option 1, plus 2 alternatives. Never book from a time the agent itself inferred.
- **After the stand-in picks:** recheck free/busy for that slot. On a conflict, re-offer 3 new slots. If it's free, insert the event. BOOKED is set only when the response has an event id and a `hangoutLink`/conference entry point. On any failure, set MEETING_READY_TO_BOOK and show the error.

### Time rules

- **Two clocks (the demo clock exists only if the follow-up stretch is built).** The demo clock (real time + offset) governs only internal scheduling: follow-up due times and attempt caps. Free/busy windows, slot generation, the "not in the past" checks, event times and inbound message timestamps all use real time.
- **Timezone:** Asia/Kolkata (the seller's) for working hours and slots.
- **Send-hours gate:** the spec §8.4 Mon-Fri 09:00-18:00 rule is implemented and unit-tested, and LIVE campaigns always use it. STAND_IN campaigns use a documented demo window of any time, so a Saturday-evening demo isn't blocked. The UI shows "Demo send window: any time."

### REPLAY fallback (only if time allows; on the cut list)

- **Scope:** Crustdata responses only. LLM, Gmail and Calendar stay live.
- **Recording:** every live Crustdata call made during the pre-run is cached to `data/replay/` (gitignored).
- **Trigger:** a manual top-bar toggle. If a Crustdata call fails or times out (>15s), the UI suggests switching but never switches on its own.
- **Badge:** while any replayed data is on screen, the top-bar badge reads REPLAY instead of LIVE DATA.

### Supported ICP constraints

The deterministic scorer evaluates PASS/FAIL/UNKNOWN only on these fields:

- company country
- headcount (range)
- industry (exact match against Crustdata's values)
- open roles matching keywords (from `job_search`)
- headcount growth over 12 months (if present in the record)

Any other constraint the LLM proposes is shown as "not machine-checkable." It can't be marked mandatory, and if kept as a preference it always evaluates UNKNOWN, so it lowers coverage, not fit.

### Discovery shortfall

- If fewer than 20 companies pass all mandatory criteria, run one widened query that drops low-priority preferences only (spec §6.2, BALANCED).
- If still short, show "20 target · N qualified" honestly.
- Companies with any mandatory criterion UNKNOWN (NEEDS_EVIDENCE) appear in a separate section below the ranked list. They are never contactable and never count toward the 20.

### OAuth timebox and fallback

- **Checkpoint at 2:30:** by then, the app must do an in-app Gmail send to the stand-in plus one successful in-app Calendar `freebusy.query`, using the stored OAuth token. If not, fall back to Approach A's transport (SMTP send, IMAP read, `.ics` invite) behind the same interfaces, with the same recipient guard.
- **Fallback slots and matching:** slots come from working hours only, labeled "not free/busy-checked." IMAP replies are matched by `In-Reply-To`/`References` against stored outbound `Message-ID`s, plus the same From check.
- **Booking in fallback mode:** an emailed `.ics` has no event id or Meet link, so the outcome is MEETING_READY_TO_BOOK with the label "Invite sent (.ics), not calendar-verified." It is never BOOKED, and Success Criterion 4 is reported as not met in that mode.

**Wireframe (approved, D7):** `docs/assets/wireframe-campaign.png` (source: `docs/assets/wireframe-campaign.html`)
- Top bar: LIVE DATA badge (REPLAY only if built), delivery-mode badge, Pause. The demo clock and Fast-forward appear only if the follow-up stretch is built.
- Left: funnel, then ranked prospects with fit and coverage as separate columns and `[src]` receipt chips.
- Right: agent journal with the booked-meeting card pinned on top.

## Open Questions

1. **Crustdata REST paths.** The app calls the REST API, not MCP. Confirmed on the tested key: `POST /company/search` (supports `search` natural language or `filters`; ranked search max 100, no sorts), `POST /job/search`, `POST /person/search`, `POST /person/enrich` (business emails via `fields: ["contact.business_emails"]`, 15 rpm). `/person/contact/enrich` is DISABLED on that key. All calls use `Authorization: Bearer $CRUSTDATA_API_KEY` and `x-api-version: 2025-11-01`. At 0:00, re-check the event-issued key's endpoints and read the exact request/response field names from https://docs.crustdata.com before coding each adapter method; do not guess field names.
2. **Stand-in identity.** Is it the judge (needs consent and their email before the demo) or the builder's second Gmail? Recommendation: rehearse with your own second account, and use the judge live only if they agree.
3. **Real names on a projector: decided.** Emails are never shown in the UI; it shows "verified ✓" instead. Names and titles (public professional info from Crustdata) are shown for all contacts.
4. **LLM provider: resolved.** The team has keys for all major AI providers. [user: "we all have all ai api keys btw"] At 0:00, pick one provider for all LLM steps (product profile, ICP, drafts with typed sentences, reply classification). Choose it for reliable schema-constrained JSON output, since the claim gate and classifier depend on it. Keep the adapter narrow so the provider can be swapped if one is slow or rate-limited during the demo.

## Success Criteria

On stage, in about 2.5 minutes, following the stage plan above:

1. With discovery pre-run on live data, the UI shows up to 20 real, ranked companies, and clicking `[src]` opens the evidence drawer with the raw Crustdata record.
2. Clicking Send delivers the featured email to the stand-in inbox, and only there.
3. The stand-in replies "interested." After "Check inbox now," the agent sends 3 numbered, free/busy-checked slots within 30 seconds.
4. The stand-in replies "2." After "Check inbox now," a Calendar event with a Meet link appears in the seller's and stand-in's calendars. The UI shows BOOKED with the event id.

**Product checks (tested before code freeze, not shown on stage):**

5. A "remove me" reply on a second STAND_IN rehearsal campaign suppresses that contact, and no later send to it happens in any campaign.
6. With `OUTBOUND_ENABLED=false`, creating a LIVE campaign is refused. With it `true` but no consent record, the provider guard rejects the send. Covered by unit tests; no real email is sent during the hackathon unless the seller deliberately runs LIVE after the event.

**Stretch (only if ahead at 3:30):** on a separate STAND_IN rehearsal campaign whose one delivered contact gets no reply, "Fast-forward 3 days" sends follow-up 1, the contact caps at 2 follow-ups, then goes EXHAUSTED.

## Distribution Plan

The demo runs locally on the presenting laptop (`make dev` or two terminals). Submission is a GitHub repo with a README and `.env.example`. No deploy needed.

## Next Steps (time-boxed)

- **First action, before the build clock starts (and within 7 days of the demo):** create the Google Cloud project and OAuth client, enable the Gmail and Calendar APIs, add the seller as a test user, and run one 20-line script that calls `events.insert` with `conferenceDataVersion=1` and gets a Meet link back. This proves the riskiest piece first.
**5-hour plan:**

| Time | Work |
|---|---|
| 0:00-0:30 | Verify the hackathon Crustdata key (`account_endpoints`), confirm the REST paths (Open Question 1), pick the LLM key. FastAPI and SQLite models (campaign with `delivery_mode` and consent fields, company, contact, evidence, message, processed_message, meeting, suppression, audit_event). Next.js shell from the wireframe. `data/` in `.gitignore`. |
| 0:30-1:30 | Crustdata discovery, job signals, §6.3 scoring, shortfall rule, prospect table with the receipt drawer. |
| 1:30-2:30 | People search, contact enrich (verified), LLM drafts with the claim gate, send gates, provider recipient guard for both modes, Gmail send. **OAuth checkpoint at 2:30.** |
| 2:30-3:30 | Inbox poll with lock and ledger, opt-out override, classification, suppression, HELD and NEEDS_HUMAN. Free/busy, numbered slots, parser, recheck, `events.insert` with deterministic id and Meet, BOOKED and MEETING_READY_TO_BOOK. |
| 3:30-4:15 | LIVE mode: consent form, env flag, red badge, guard tests. Journal panel and booked card. |
| 4:15-5:00 | Pre-run discovery, one full dry run on the stand-in, `make reset-demo`, rehearse the script, README and `.env.example`, code freeze. |

**Cut for the 5-hour clock (not built unless ahead):** follow-ups and the demo clock (stretch), REPLAY recording, URL intake, email masking (emails are hidden entirely instead), a second dry run.

**If behind at 3:30:** drop LIVE mode entirely (`DEMO_MODE` refuses LIVE, no consent form) and keep the 4:15 dry run. The product then ships STAND_IN-only, and the README says LIVE is the next step.

**Never cut:** pre-run discovery with receipts, claim gate, provider recipient guard, featured send, opt-out suppression, INTERESTED classification, numbered slots, NEEDS_HUMAN buttons, booking with the BOOKED rule, idempotency lock and ledger. If LIVE is built at all, its consent gating ships with it.


## Decisions made after the design review

- **Email source (CEO-1):** use `/person/enrich` with `fields: ["contact.business_emails"]`. Respect its 15 requests/min limit (queue with a rate limiter during the pre-run). Use `/person/contact/enrich` only if the event key enables it. Gate sends on `contact.business_emails[].status`; decide the accepted status values at 0:00 after seeing real data, and default to accepting only the strongest value.
- **ICP editing deferred (CEO-2):** show the generated ICP read-only with Approve and Regenerate. Enforce "only supported fields can be mandatory" at generation time.
- **LIVE mode kept:** build it in the 3:30-4:15 slot; drop it entirely if behind at 3:30.
- **Not yet reviewed:** architecture, error handling, security and test-plan review sections were not run. Treat the safety rules and unit tests named above as the minimum.

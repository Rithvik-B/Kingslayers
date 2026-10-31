# PLAN.md: the build contract (Kingslayers, ContextCon 03)

**This file wins over every other doc.** If anything in `docs/reference/` disagrees with this file, follow
this file. Do not build anything that isn't listed here. Do not edit a file you don't own (see §3).

Deadline: **code freeze 15:10 IST today (2026-10-31).** Three people (P1, P2, P3), each running their own
Claude Code on their own Max account, build in parallel on `main` with strict file ownership. Then we
integrate, test, fix and demo.

---

## 0. What we're building

A seller enters a product description. The agent then:
1. Builds a product profile and an ICP with the LLM. The seller approves it.
2. Finds **real** Indian companies through **live Crustdata REST**.
3. Scores and ranks them with deterministic code, and attaches a `[src]` receipt to every fact.
4. Finds the right person at each company and gets their verified business email.
5. Writes a typed, evidence-cited email draft. Code drops every uncited prospect fact (the claim gate).
6. Sends **one** email, after the seller clicks Send. In `STAND_IN` mode it always goes to the stand-in
   inbox, never to the real prospect.
7. Reads the reply from Gmail, classifies it, and offers 3 numbered slots that are free on the seller's
   calendar.
8. When the stand-in replies "2", books a **Google Calendar event with a Meet link**.

**What makes us different: every claim has a receipt.** Any company pick, score, "why now" signal or
prospect fact in an email can be clicked to show the raw Crustdata record behind it.

**BOOKED** means a calendar event id **and** a Meet link came back from Google. A sent email, a positive
reply or an `.ics` file is not BOOKED.

## 1. Final stack (all decided; don't substitute)

| Layer | Use | Don't use |
|---|---|---|
| Backend | Python 3.12, FastAPI, uvicorn, Pydantic v2, SQLAlchemy 2 (sync) + SQLite at `data/app.db` (`create_all`) | Postgres, Alembic, Docker, Celery, APScheduler |
| Frontend | **One page**, `app/static/index.html`, served by FastAPI. Tailwind from CDN, vanilla JS, polls the API every 3 s | Next.js, React, a build step |
| Company and people data | **Crustdata REST** via `httpx.AsyncClient`. Headers: `Authorization: Bearer $CRUSTDATA_API_KEY` and `x-api-version: 2025-11-01` | Crustdata skills, plugin or MCP in the app |
| Email and calendar | **Composio Python SDK** (`composio`), Gmail and Google Calendar toolkits, connected to the seller account under `COMPOSIO_USER_ID` | Our own Google Cloud OAuth, SMTP, IMAP, `.ics` |
| Reading replies | **Polling**: the app fetches known Gmail threads through Composio every 15 s, plus a "Check inbox now" button. One `asyncio.Lock` | Composio triggers, webhooks, tunnels |
| LLM | **Claude through the Claude Agent SDK** (`claude-agent-sdk`) on the developer's own Claude Max login. JSON output via `output_format` with a JSON schema. No tools, `setting_sources=[]`. Backup behind the same adapter: the `anthropic` SDK with `BACKUP_ANTHROPIC_API_KEY` | Any other provider. Never set `ANTHROPIC_API_KEY` in the environment: it overrides the Max login |
| Demo machine | Rithvik's laptop: `uvicorn app.main:app --port 8000`, logged in to Claude Code as Rithvik | Cloud hosting |

`requirements.txt` (P1 commits it exactly like this; nobody else edits it):
```
fastapi
uvicorn[standard]
httpx
sqlalchemy>=2
pydantic>=2
python-dotenv
composio
claude-agent-sdk
anthropic
pytest
pytest-asyncio
```

Set up the virtualenv: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`

## 2. Environment variables (`.env`, never committed)

Rithvik shares the real values privately (DM). They never go in git or chat logs.

```
CRUSTDATA_API_KEY=
CRUSTDATA_API_VERSION=2025-11-01
COMPOSIO_API_KEY=
COMPOSIO_USER_ID=            # user_id the seller's Gmail + Google Calendar are connected under in Composio
SELLER_EMAIL=                # the connected seller Gmail address
SELLER_NAME=Kingslayers Demo
STAND_IN_EMAIL=              # the demo recipient inbox (replies from a phone on stage)
LLM_BACKEND=agent_sdk        # agent_sdk | anthropic_api
LLM_MODEL=sonnet             # Agent SDK model alias
BACKUP_ANTHROPIC_API_KEY=    # used only when LLM_BACKEND=anthropic_api; never name it ANTHROPIC_API_KEY
BACKUP_ANTHROPIC_MODEL=claude-sonnet-5-5
DEMO_MODE=true               # true on the stage laptop: refuses to create LIVE campaigns
OUTBOUND_ENABLED=false       # global kill switch for LIVE sends
TIMEZONE=Asia/Kolkata
DISCOVERY_COMPANY_LIMIT=20   # use 5 while developing, to save credits
CONTACTS_PER_COMPANY=1
CREDIT_CEILING_PER_RUN=150
ACCEPTED_EMAIL_STATUSES=verified,valid   # P2 confirms the real values at 14:15
```

## 3. Repo layout and ownership (only the owner edits a file)

```
app/__init__.py            P1   (empty)
app/config.py              P1   settings object `S` read from env (python-dotenv)
app/db.py                  P1   engine, SessionLocal, init_db(), session() context manager
app/models.py              P1   tables, FROZEN contract in §5 (copy exactly)
app/journal.py             P1   log() for the agent journal
app/main.py                P1   FastAPI app, every route in §7, background inbox loop, static page
app/static/index.html      P1   the whole UI (§8)
app/llm.py                 P2   LLM adapter (§6.1)
app/crustdata.py           P2   REST client (§6.2)
app/scoring.py             P2   deterministic scoring (§6.3)
app/discovery.py           P2   ICP generation and the discovery pipeline (§6.4)
app/drafting.py            P2   email drafts and the claim gate (§6.5)
app/gates.py               P3   send gates (§6.6)
app/mail.py                P3   Composio Gmail + recipient guard (§6.7)
app/calendar_io.py         P3   Composio Calendar + recipient guard (§6.8)
app/outreach.py            P3   send_initial (§6.9)
app/inbox.py               P3   inbox pass, strip, opt-out, classify, actions (§6.10)
app/booking.py             P3   slots, offer email, slot parsing, booking (§6.11)
scripts/smoke_crustdata.py P2
scripts/smoke_composio.py  P3
tests/test_scoring.py      P2
tests/test_claim_gate.py   P2
tests/test_guard.py        P3
tests/test_inbox.py        P3
requirements.txt, .env.example, README.md   P1
data/                      gitignored (DB, caches)
```

Rules:
- **Code against the contracts in §5–§6 even before the other person has pushed.** If you need their
  function to run something locally, stub it in a scratch file you don't commit.
- **If a contract must change, the owner changes it and says so in the team chat.** Never edit someone
  else's file.
- **Imports go one way:** `main` imports everything. `discovery` imports `crustdata`, `scoring`, `llm`,
  `drafting`, `models` and `journal`. `inbox`, `booking`, `outreach` and `gates` import `mail`,
  `calendar_io`, `llm`, `models` and `journal`. No circular imports.
- **Every external action writes a journal line** (`journal.log`).

## 4. Timeline (IST)

| Time | P1 (Rithvik, demo laptop) | P2 (discovery) | P3 (conversation) |
|---|---|---|---|
| 14:15 | Push skeleton: requirements, config, db, models, journal, empty main with `/` + `/api/health` | Smoke-test Crustdata: real field names, email status values. Write them in `docs/notes/crustdata-rest.md` and push | Smoke-test Composio: send to stand-in, read thread, find free slots, **create event with Meet link**. Write findings in `docs/notes/composio-tools.md` and push |
| 14:15–14:40 | All routes, UI, background loop | llm, crustdata, scoring, discovery, drafting | gates, mail, calendar_io, outreach, inbox, booking |
| **14:40** | **Tier 1 pushed by everyone** | | |
| 14:40–14:55 | Run the full flow on the stand-in; owners fix their own files | fix | fix |
| 14:55–15:05 | Pre-run discovery (limit 20), `POST /api/demo/reset` of rehearsal data, rehearse §10 | Tier 2 if green | Tier 2 if green |
| 15:05–15:10 | README, final push, submit. **Freeze 15:10** | | |

**Tiers.** Tier 1 is the stage path and is never cut. Do Tier 2 only after Tier 1 passes integration.
Tier 3 is not built today; it lives in `TODOS.md`.

**Git:** everyone commits small and runs `git pull --rebase && git push` at least every 10 minutes from
14:15. Ownership never overlaps, so rebases are clean. Never force-push.

## 5. Data model (P1 writes `app/models.py` from this, exactly)

All ids are UUID strings (`str(uuid4())`). All times are timezone-aware UTC. JSON columns use
`sqlalchemy.JSON`.

| Table | Columns |
|---|---|
| `campaigns` | id, name, product_text, product_profile JSON (nullable), icp JSON (nullable), icp_approved bool=False, delivery_mode str (`STAND_IN`\|`LIVE`), status str (`DRAFT`\|`DISCOVERING`\|`READY`\|`RUNNING`\|`DONE`\|`FAILED`), paused bool=False, discovery_ran_at datetime (nullable), credits_used float=0, consent JSON (nullable; LIVE only), created_at |
| `companies` | id, campaign_id, crustdata_id str, name, domain (nullable), industry (nullable), country (nullable), city (nullable), headcount int (nullable), headcount_growth_12m float (nullable), fit float (nullable), coverage float, tier str (`T1`\|`T2`\|`T3`\|`T4`\|`NEEDS_EVIDENCE`\|`EXCLUDED`), rank int (nullable), why_now JSON = list of `{label, evidence_id}`, criteria JSON = list of `{constraint_id, field, type, verdict, observed, evidence_id}`, raw JSON |
| `contacts` | id, campaign_id, company_id, crustdata_person_id (nullable), name, title, role str (`CHAMPION`\|`ECONOMIC_BUYER`\|`OTHER`), linkedin_url (nullable), verified_email (nullable; **never sent to the UI**), email_status (nullable), state str (see §6.12), featured bool=False, thread_id (nullable), delivered_to (nullable), raw JSON |
| `evidence` | id, campaign_id, subject_type (`company`\|`contact`), subject_id, endpoint str (e.g. `/job/search`), field_path str, value str, source_url (nullable; never invented), raw_excerpt JSON, retrieved_at |
| `messages` | id, campaign_id, contact_id, direction (`out`\|`in`), kind (`initial`\|`slot_offer`\|`confirmation`\|`reply`), subject (nullable), body text, sentences JSON (nullable; drafts only), gate_status (`PASS`\|`NEEDS_REVIEW`, nullable), gate_notes JSON (nullable), status (`DRAFT`\|`HELD`\|`PENDING`\|`SENT`\|`FAILED`\|`UNKNOWN`\|`RECEIVED`), idempotency_key (unique, nullable), provider_message_id (nullable), thread_id (nullable), send_approved_at (nullable), sent_at (nullable), received_at (nullable), created_at |
| `processed_messages` | gmail_message_id (PK), contact_id (nullable), outcome str, processed_at |
| `meetings` | id, campaign_id, contact_id, slots_offered JSON = list of ISO start strings, start_at (nullable), end_at (nullable), event_id (nullable), meet_link (nullable), status (`OFFERED`\|`BOOKED`\|`MEETING_READY_TO_BOOK`), accepted_message_id (nullable), error (nullable), created_at |
| `suppressions` | id, contact_key str (normalized real email, or `contact:<id>` if there's no email), reason, source_campaign_id, source_mode, created_at |
| `journal` | id, campaign_id, contact_id (nullable), at, kind str, text str, data JSON (nullable) |

`app/journal.py`: `def log(campaign_id: str, kind: str, text: str, contact_id: str | None = None, data: dict | None = None) -> None`
opens its own session and commits.

`app/db.py`: `engine = create_engine("sqlite:///data/app.db", connect_args={"check_same_thread": False})`,
`SessionLocal`, `def init_db()` (creates `data/` and runs `Base.metadata.create_all`), and
`@contextmanager def session()`, which yields a session and commits or rolls back.

`app/config.py`: `class Settings` with one attribute per env var in §2, with the right types (bools are
`"true"`, lists are comma-separated). Expose it as `S = Settings()`.

## 6. Module contracts

### 6.1 `app/llm.py` (P2)

```python
class LLMError(Exception): ...
async def complete_json(system: str, prompt: str, schema: dict) -> dict
```
- **`agent_sdk` backend:**
  - Call `claude_agent_sdk.query(prompt=..., options=ClaudeAgentOptions(system_prompt=system, model=S.LLM_MODEL, output_format={"type": "json_schema", "schema": schema}, max_turns=3, allowed_tools=[], setting_sources=[]))`.
  - Return the `structured_output` of the result message.
  - Verify the exact names in the installed SDK by introspection before relying on them.
  - `setting_sources=[]` is mandatory. It stops our repo's CLAUDE.md and hooks from loading into app calls.
- **Before the first call,** if `ANTHROPIC_API_KEY` is in `os.environ`, raise `LLMError("unset ANTHROPIC_API_KEY: it overrides the Max login")`.
- **Concurrency:** a module-level `asyncio.Semaphore(4)`. Each call starts a `claude` process.
- **`anthropic_api` backend:** `anthropic.AsyncAnthropic(api_key=S.BACKUP_ANTHROPIC_API_KEY)` with model
  `S.BACKUP_ANTHROPIC_MODEL`. Force one tool whose `input_schema` is `schema`, and return its input.
- **Errors:** retry once, then raise `LLMError`.

### 6.2 `app/crustdata.py` (P2)

```python
class CrustdataClient:
    credits_used: float
    async def company_search(self, *, query: str, filters: dict | None, limit: int) -> list[dict]
    async def job_search(self, *, company: dict, keywords: list[str], limit: int = 10) -> list[dict]
    async def person_search(self, *, company: dict, titles: list[str], limit: int = 5) -> list[dict]
    async def person_enrich(self, *, linkedin_url: str) -> dict   # fields=["contact.business_emails"]
```
- **Endpoints:** `POST https://api.crustdata.com/company/search` (natural-language `search` or `filters`;
  max 100), `/job/search`, `/person/search`, `/person/enrich`. **`/person/contact/enrich` is disabled on
  our key; don't use it.**
- **Don't guess field names.** At 14:15, read https://docs.crustdata.com for each endpoint and make one tiny
  real call per endpoint (`scripts/smoke_crustdata.py`). Write the request and response field names into
  `docs/notes/crustdata-rest.md`. Re-check the key's enabled endpoints (the free `account_endpoints`
  check, `docs/notes/crustdata-endpoints.md`).
- **`person_enrich` limit is 15 requests per minute:** use a rate limiter that spaces calls 4.2 s apart.
- **Credits and retries:** add `credits_used` from each response if present, otherwise an estimate. Raise
  `CreditCeilingReached` when `credits_used > S.CREDIT_CEILING_PER_RUN`. Use a 15 s timeout, and retry once
  on 429/5xx with backoff.

### 6.3 `app/scoring.py` (P2)

```python
def evaluate(constraint: dict, company: dict, jobs: list[dict]) -> tuple[str, object, str | None]
    # returns (verdict PASS|FAIL|UNKNOWN, observed_value, field_path)
def score(criteria: list[dict]) -> dict   # returns {"fit": float | None, "coverage": float, "tier": str}
```
- **Machine-checkable fields:** `country`, `headcount` (range), `industry` (exact match against
  Crustdata's values), `open_roles` (job titles that match the keywords; count ≥ 1), and
  `headcount_growth_12m`. Anything else always gives `UNKNOWN` and can never be mandatory.
- **Formula (long spec §6.3):**
  - `known` = the summed weight of preferred criteria that evaluated PASS or FAIL
  - `passed` = the summed weight of preferred criteria that evaluated PASS
  - `fit = 100 * passed / known`, or `None` when `known` is 0
  - `coverage = 100 * known / all_preferred_weight`, or 100 when there are no preferred criteria
- **Tiers:**
  - Any mandatory FAIL: `EXCLUDED`.
  - Otherwise, any mandatory UNKNOWN: `NEEDS_EVIDENCE`.
  - Otherwise `T1` if every preferred criterion PASSed and coverage ≥ 80, `T2` if fit ≥ 80 and
    coverage ≥ 60, `T3` if fit ≥ 60 and coverage ≥ 50, else `T4`.
- **Ranking order:** tier, then fit (with `None` last), then coverage, then `crustdata_id`.

### 6.4 `app/discovery.py` (P2)

```python
async def generate_profile_and_icp(campaign_id: str) -> None
async def run_discovery(campaign_id: str) -> None   # requires icp_approved; journals each stage
```
- **ICP generation:** one LLM call with the schema below. Code then forces any constraint whose field isn't
  machine-checkable to `PREFERRED` and labels it "not machine-checkable". Save the result on the campaign.
  ```json
  {"product_profile": {"name": "str", "category": "str", "value_proposition": "str", "capabilities": ["str"], "target_departments": ["str"], "problems": ["str"]},
   "icp": {"nl_query": "str", "person_titles": ["str"], "job_keywords": ["str"],
           "constraints": [{"id": "str", "field": "country|headcount|industry|open_roles|headcount_growth_12m|other",
                            "type": "MANDATORY|PREFERRED", "operator": "eq|in|between|gte", "expected": "any",
                            "weight": 0, "importance": "critical|high|medium|low", "relaxable": false, "rationale": "str"}]}}
  ```
- **The pipeline:**
  1. `status=DISCOVERING`.
  2. `company_search` with `icp.nl_query`, plus country and headcount filters if mandatory, and
     `limit = 3 × DISCOVERY_COMPANY_LIMIT` (at most 60).
  3. `job_search` for each company in parallel (`asyncio.gather`) with `icp.job_keywords`.
  4. Evaluate and score. Write the `companies` rows and one `evidence` row per observed field. Each
     criterion stores its `evidence_id`, and each `why_now` chip stores the job-postings or growth evidence.
  5. **Shortfall:** if fewer than `DISCOVERY_COMPANY_LIMIT` companies are eligible, re-run once without the
     low-importance relaxable preferences. Then report "N target · M qualified" honestly.
  6. For the top `DISCOVERY_COMPANY_LIMIT` eligible companies, run `person_search` with
     `icp.person_titles`. Role labels: Head or VP or Director of Talent and HR is `CHAMPION`; CHRO, CPO or
     VP People is `ECONOMIC_BUYER`. Keep `CONTACTS_PER_COMPANY`.
  7. `person_enrich` for business emails. The email is verified when its status is in
     `ACCEPTED_EMAIL_STATUSES`. Set `state=READY` with `verified_email`, otherwise `state=UNREACHABLE`.
     Store the email's evidence row (field `contact.business_emails.status`, value is the status only, not
     the email).
  8. `featured` = the top-ranked `T1` contact (or `T2` if there's no `T1`) that is `READY`.
  9. `await drafting.generate_drafts(campaign_id)`.
  10. Set `discovery_ran_at=now` and `status=READY`. Save `credits_used`.
- **On `CreditCeilingReached`:** stop, journal a warning, and keep what's done.

### 6.5 `app/drafting.py` (P2)

```python
async def generate_drafts(campaign_id: str) -> None
def claim_gate(sentences: list[dict], allowed_evidence_ids: set[str], profile: dict) -> tuple[list[dict], str, list[str]]
    # returns (kept_sentences, "PASS" | "NEEDS_REVIEW", notes)
def opt_out_line(campaign) -> str
```
- **One draft per `READY` contact**, all in parallel. The LLM gets the product profile, the company facts as
  `{evidence_id, field, value}` (only this company's and contact's evidence), and the contact's name,
  title and role. Schema:
  `{"subject": "str", "sentences": [{"type": "prospect_fact|product_fact|hypothesis|cta", "text": "str", "evidence_ids": ["str"], "profile_field": "str|null"}]}`
- **Prompt rules:**
  - 70–110 words.
  - One concrete "why now" prospect fact.
  - Hypotheses worded as questions or with "might".
  - One CTA asking for a 20-minute call.
  - No invented customers, metrics, relationships or availability.
  - Don't write an opt-out line; code adds it.
- **The claim gate:**
  - Drop any `prospect_fact` that has no evidence id in `allowed_evidence_ids`.
  - Drop any `product_fact` whose `profile_field` doesn't exist in the profile (for example
    `capabilities[2]` or `value_proposition`).
  - The draft is `NEEDS_REVIEW` if fewer than one `prospect_fact` or no `cta` is left.
- **Body:** the kept sentences joined, then `opt_out_line()` appended by code:
  - STAND_IN: `"If this isn't relevant, just reply 'remove me' and I won't email again."`
  - LIVE: the same sentence, plus the sender name and postal address from the consent record.
- **Message row:** `direction=out`, `kind=initial`, `status=DRAFT`. In `STAND_IN`, every passing draft
  except the featured contact's gets `status=HELD`, and that contact's `state=HELD` (deliver 1, hold the
  rest).

### 6.6 `app/gates.py` (P3)

```python
def can_send(campaign, contact, kind: str) -> tuple[bool, str]   # kind: initial|slot_offer|confirmation|book
```
Every check runs right before every external action. Return `(False, reason)` on the first one that fails:
1. The campaign is not paused.
2. The contact has `verified_email`, and its `email_status` is accepted.
3. The contact isn't suppressed: no `suppressions` row for its normalized email or `contact:<id>`.
4. The state is sendable: `READY` for `initial`, `WAITING` or `SCHEDULING` otherwise.
5. Caps: `initial` only once per contact. In STAND_IN, at most **1** delivered contact per campaign. In LIVE,
   the consent's `max_sends`, and at most 10 initial sends per day.
6. Time: LIVE only Mon–Fri 09:00–18:00 Asia/Kolkata. STAND_IN any time (UI shows "Demo send window: any time").

### 6.7 `app/mail.py` (P3)

```python
class RecipientGuardError(Exception): ...
def delivered_recipient(campaign, contact) -> str   # STAND_IN -> S.STAND_IN_EMAIL; LIVE -> contact.verified_email
def check_recipient(campaign, contact, to_email: str, *, initial: bool) -> None
async def send_email(campaign, contact, *, kind: str, subject: str, body: str, thread_id: str | None, idempotency_key: str) -> dict
    # returns {"message_id": str, "thread_id": str}
async def fetch_thread(thread_id: str) -> list[dict]
    # returns [{"id", "from", "to", "date", "subject", "text", "label_ids"}]
```
- **`check_recipient` is the safety core, and fails closed.** It runs inside `send_email`, immediately before
  the Composio call.
  - STAND_IN: `to_email` must equal `STAND_IN_EMAIL`. Anything else raises `RecipientGuardError`.
  - LIVE: requires `OUTBOUND_ENABLED` (read at call time), `DEMO_MODE` false, consent present and not past
    its end date, the caps from §6.6, and `to_email == contact.verified_email`.
- **Idempotency:**
  - Write a `PENDING` message row with `idempotency_key` (contact + step + attempt, e.g. `c42:slot_offer:2`)
    before the call. If that key already exists, don't send.
  - A clear error marks the row `FAILED`. A timeout marks it `UNKNOWN`, and it is never re-sent
    automatically.
- **Replies stay in the thread.** Send them with the stored `thread_id` through Composio's
  reply-to-thread tool.
- **Composio:** `Composio(api_key=S.COMPOSIO_API_KEY)` and `composio.tools.execute(<SLUG>, user_id=S.COMPOSIO_USER_ID, arguments={...})`.
  The SDK is sync, so wrap calls in `asyncio.to_thread`. At 14:15, verify the slugs and argument names from
  the installed SDK or Composio's toolkit pages (expected: `GMAIL_SEND_EMAIL`, `GMAIL_REPLY_TO_THREAD`, a
  fetch-thread tool). Record them in `docs/notes/composio-tools.md`. Composio's `initiate()` is retired;
  connections already exist.

### 6.8 `app/calendar_io.py` (P3)

```python
async def free_slots(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]  # 20-min, 09:00-18:00 IST, 10-min buffers
async def is_free(start: datetime, end: datetime) -> bool
async def create_meeting(campaign, contact, meeting_id: str, *, start, end, title: str, description: str) -> dict
    # returns {"event_id": str | None, "meet_link": str | None}
```
- **Tools:** `GOOGLECALENDAR_FIND_FREE_SLOTS` or `GOOGLECALENDAR_FREE_BUSY_QUERY`, and
  `GOOGLECALENDAR_CREATE_EVENT` with `create_meeting_room=True`, `attendees=[delivered_recipient]` and
  `send_updates="all"`. Run `mail.check_recipient` on the attendee before the call.
- **Avoiding double bookings:** put the marker `[kingslayers-mtg:<meeting_id>]` in the description. Before
  creating, search that day's events for the marker. If a non-cancelled one exists, return it instead of
  creating another.
- **The Meet-link risk (test it at 14:15):** Composio's docs say personal Gmail accounts may get **no Meet
  link** from `CREATE_EVENT`. If the smoke test shows that, connect the Google Meet toolkit for the same
  `COMPOSIO_USER_ID`, create a space with `GOOGLEMEET_CREATE_MEET`, and put its real link in the event's
  location and description. Return that as `meet_link`. Never invent a link.

### 6.9 `app/outreach.py` (P3)

```python
async def send_initial(contact_id: str) -> None
```
- **Requirements:** the draft's `gate_status=PASS`, `send_approved_at` set (the route sets it), and
  `gates.can_send(...)` ok.
- **Sending:** `mail.send_email(kind="initial", idempotency_key=f"{contact_id}:initial:1")`.
- **After the send:** save `contact.thread_id` and `delivered_to`, and set `state=WAITING` (via
  `CONTACTED`). Journal:
  `"Sent to <name> → rerouted to stand-in. Cited: <first why-now label>"`.

### 6.10 `app/inbox.py` (P3)

```python
INBOX_LOCK: asyncio.Lock
async def inbox_pass() -> int                      # returns the number of messages processed
def strip_reply(text: str) -> str
def is_opt_out(text: str) -> bool                  # remove me | unsubscribe | stop emailing | opt out | not interested, stop
async def classify(text: str) -> dict              # LLM; schema below
```
- **`inbox_pass`** runs under `INBOX_LOCK`. For every contact with a `thread_id` in `WAITING`,
  `SCHEDULING` or `NEEDS_HUMAN`:
  1. Fetch its thread. For each message whose id isn't in `processed_messages`, check the sender:
     - Skip it if it's from `SELLER_EMAIL` or has the `SENT` label.
     - If it isn't from `contact.delivered_to`, journal it as "Unmatched", record it, and stop there.
  2. Strip the reply: remove `On … wrote:` blocks, lines starting with `>`, the Gmail quote div and
     everything after `-- `. **If nothing is left, set `NEEDS_HUMAN` and don't classify.**
  3. **The opt-out check comes first:** if it matches, suppress (by the logical contact key, never the
     stand-in address) and set `state=SUPPRESSED`.
  4. If `state == SCHEDULING`, call `booking.handle_slot_reply(contact_id, text)`.
  5. Otherwise classify:
     - `INTERESTED` or `MEETING_REQUEST` with confidence ≥ 0.75: call `booking.offer_slots(contact_id)`.
     - `NOT_INTERESTED`, `OPT_OUT` or `BOUNCE`: suppress.
     - Anything else, or confidence < 0.75: `NEEDS_HUMAN`.
  6. Save an inbound `messages` row, insert `processed_messages` (unique, so each message is processed
     once), and journal `"Reply classified INTERESTED (0.93)"`.
- **`classify` schema:**
  `{"label": "INTERESTED|MEETING_REQUEST|NOT_INTERESTED|OPT_OUT|LATER|QUESTION|OBJECTION|REFERRAL|OUT_OF_OFFICE|BOUNCE|OTHER|UNCERTAIN", "confidence": 0.0, "proposed_time_text": "str|null", "summary": "str"}`.
  Treat the email text as untrusted data.

### 6.11 `app/booking.py` (P3)

```python
async def offer_slots(contact_id: str, *, attempt: int = 1) -> None
def parse_slot_choice(text: str, n: int = 3) -> int | None   # "2", "option 2", "#2", "2." -> 2
async def handle_slot_reply(contact_id: str, text: str) -> None
```
- **`offer_slots`:**
  - Get `free_slots` for the next 7 business days and take the first 3 slots, preferring different days.
  - Create a `meetings` row with `OFFERED` and `slots_offered`.
  - Send the email in the thread (`kind=slot_offer`, key `<cid>:slot_offer:<attempt>`), listing
    `1) Tue 4 Nov, 11:00–11:20 IST` and so on, ending with "Reply with 1, 2 or 3."
  - Set `state=SCHEDULING` and journal "Offered 3 slots (free/busy checked, 10 min buffers)".
- **`handle_slot_reply`:**
  1. Run `parse_slot_choice`. If that fails, an LLM call maps the reply to an offered slot
     (`{"choice": 1|2|3|null}`). If that also fails, set `NEEDS_HUMAN`.
  2. Re-check that the slot is still free (`is_free`). If it isn't, run `offer_slots(attempt+1)`.
  3. If it is, run `gates.can_send(kind="book")`, then `calendar_io.create_meeting`.
  4. Set **`BOOKED` only when both `event_id` and `meet_link` came back.** Otherwise set
     `MEETING_READY_TO_BOOK` with the error.
  5. Save the meeting (start, end, event_id, meet_link, accepted_message_id), set `contact.state`, and
     journal "Calendar event created, invite sent. Marked BOOKED."
- **Tier 2:** if the first reply proposes its own time (`proposed_time_text`), offer that time as option 1
  plus 2 alternatives.

### 6.12 Contact states

```
READY → WAITING (initial sent)         READY → HELD (STAND_IN, not featured)      READY/UNREACHABLE (no verified email)
WAITING → SCHEDULING (interested → slots offered)    WAITING → SUPPRESSED (opt-out/not interested/bounce)
WAITING → NEEDS_HUMAN (other label, low confidence, empty text)
SCHEDULING → BOOKED | MEETING_READY_TO_BOOK | SCHEDULING (conflict → re-offer) | NEEDS_HUMAN (unparseable) | SUPPRESSED
NEEDS_HUMAN → SCHEDULING ("Treat as interested") | SUPPRESSED ("Suppress") | WAITING ("Dismiss")
```
- `HELD` is terminal: nothing ever sends a held draft.
- Pause blocks every external action: sends, slot offers and bookings.

## 7. API routes (P1, `app/main.py`)

- **App startup:** `init_db()`, then start a background task that runs `inbox.inbox_pass()` every 15 s
  (catch and log errors; never crash).
- **All routes are JSON under `/api`.** Never return `verified_email`; return `"email_verified": true`
  instead.

| Method | Route | Does |
|---|---|---|
| GET | `/` | serves `app/static/index.html` |
| GET | `/api/health` | `{"ok": true}` |
| POST | `/api/campaigns` | `{name, product_text, delivery_mode}`. LIVE is refused when `DEMO_MODE` is true or `OUTBOUND_ENABLED` is false |
| GET | `/api/campaigns` | list |
| POST | `/api/campaigns/{id}/icp` | `discovery.generate_profile_and_icp` (regenerate = call again) |
| POST | `/api/campaigns/{id}/icp/approve` | `icp_approved=True` |
| POST | `/api/campaigns/{id}/discover` | runs `discovery.run_discovery` as a background task, returns immediately |
| GET | `/api/campaigns/{id}` | campaign, plus funnel `{discovered, qualified, target, contacts, verified, emailed, drafted, held, replied, booked}` and `discovery_ran_at` |
| GET | `/api/campaigns/{id}/companies` | ranked list (with why_now, criteria, contacts and the contact status), plus a separate `needs_evidence` list |
| GET | `/api/evidence/{id}` | one evidence row, for the `[src]` drawer |
| GET | `/api/contacts/{id}/draft` | the latest initial draft, with sentences, each cited evidence value or profile field value, gate status and notes |
| POST | `/api/contacts/{id}/feature` | moves the star to this contact (before any send) |
| POST | `/api/contacts/{id}/send` | sets `send_approved_at`, then `await outreach.send_initial(id)`. Returns the error text on a gate or guard failure |
| POST | `/api/inbox/check` | `await inbox.inbox_pass()` ("Check inbox now") |
| POST | `/api/contacts/{id}/human/{action}` | `treat_interested` → `booking.offer_slots`; `suppress`; `dismiss` → `WAITING` |
| POST | `/api/campaigns/{id}/pause` and `/resume` | sets `paused` |
| GET | `/api/campaigns/{id}/journal` | newest first |
| GET | `/api/campaigns/{id}/meetings` | meetings (for the booked card) |
| POST | `/api/demo/reset` | deletes STAND_IN campaigns and all their rows, including suppressions they created. **Never touches LIVE rows** |
| POST | `/api/campaigns/{id}/consent` | **Tier 2:** LIVE consent record `{sender_name, company, postal_address, max_sends (default 5), end_date, authorized: true}` |

## 8. The UI (P1, `app/static/index.html`)

The layout follows `docs/assets/wireframe-campaign.png`.

- **Top bar:**
  - campaign name
  - `LIVE DATA · Crustdata` badge
  - delivery badge: `STAND-IN: sends go to <stand-in, masked like j***@gmail.com>` (amber), or `LIVE: real prospects` (red)
  - "Discovery ran at HH:MM on live Crustdata"
  - "Demo send window: any time"
  - **Pause** button
- **Setup panel** (shown when the campaign isn't ready yet):
  - product textarea, prefilled with the demo product (§10), and **Create campaign**
  - **Generate ICP**, which shows the profile and ICP read-only, with machine-checkable versus "not
    machine-checkable" tags and MANDATORY/PREFERRED. Buttons: **Approve**, **Regenerate**.
  - **Run discovery**, with a spinner and journal lines streaming in
- **Left side:**
  1. **Funnel:** Discovered, Qualified ("20 target · N qualified" when short), Contacts ("N w/ verified
     email"), "Emailed 1 · Drafted N (M held)", Replied, Booked.
  2. **Ranked table:** #, company (with industry, headcount, city), tier, fit, coverage, why-now chips each
     with a `[src]` link, contact (name, title, role, "email verified ✓" or "no email → manual task"), a
     status pill and a ⭐ featured marker.
  3. A **NEEDS_EVIDENCE** section below the table.
- **Draft panel** (opens when a contact is clicked): subject, then each sentence with its type tag.
  - `prospect_fact` shows the cited value and its `[src]`.
  - `product_fact` shows the cited profile field.
  - Then the gate status, and a **Send** button, enabled only for the featured contact with
    `gate_status=PASS`.
- **Right side:**
  - **Agent journal**, newest first, with timestamps, plus a **Check inbox now** button.
  - The **booked card**, pinned on top once BOOKED: date and time in IST, the contact and company, the Meet
    link, "event id ✓", and the reply that accepted.
- **NEEDS_HUMAN rows** show the reply text and three buttons: Treat as interested, Suppress, Dismiss.
- **`[src]` drawer:** shows endpoint, field path, value, retrieved_at and the raw JSON excerpt, plus the
  source URL if one exists.
- **Polling:** the page re-fetches the campaign, companies, journal and meetings every 3 s.

## 9. Tests (write them; run with `.venv/bin/pytest -q`)

- **P3 `tests/test_guard.py`:**
  - A real address in STAND_IN raises.
  - A LIVE campaign without consent raises.
  - `OUTBOUND_ENABLED=false` blocks a consented LIVE send.
  - With LIVE `max_sends=1` and one contact already delivered, a slot offer to that contact passes and an
    initial send to a second contact is rejected.
- **P3 `tests/test_inbox.py`:**
  - An "interested" reply that quotes the opt-out line is **not** suppressed.
  - A "2" reply that quotes the slot list parses as 2.
  - A reply that is empty after stripping goes to `NEEDS_HUMAN`.
  - The `parse_slot_choice` variants all parse.
- **P2 `tests/test_scoring.py`:** zero evaluable criteria, zero weights, a mandatory FAIL gives `EXCLUDED`,
  and a mandatory UNKNOWN gives `NEEDS_EVIDENCE`.
- **P2 `tests/test_claim_gate.py`:** an uncited prospect fact is dropped, a draft with no prospect fact left
  is `NEEDS_REVIEW`, and a bad `profile_field` is dropped.

## 10. Demo (3 min) and its input

**Demo product text** (prefilled in the UI):
"TalentFlow: an AI tool that screens applicants and coordinates recruitment pipelines for medium and large
employers in India (200+ employees). Helps talent-acquisition teams cut time-to-hire when hiring volume
spikes."

**Before going on stage:**
1. Run discovery with `DISCOVERY_COMPANY_LIMIT=20`, 10–20 minutes before the demo.
2. Rehearse once on a separate campaign.
3. Clear the rehearsal with `/api/demo/reset`. That deletes every STAND_IN campaign, so pre-run again
   afterwards, or run it before the main pre-run.

**On stage (about 2.5 minutes):**
1. Show the ranked table and click 2 `[src]` receipts (40 s).
2. Open the ⭐ featured draft and point to its receipts (20 s).
3. Click **Send**. The email lands on the stand-in's phone (5 s).
4. The stand-in replies "Interested, send times". Click **Check inbox now**, and the journal shows
   INTERESTED and 3 slots sent (30 s).
5. The stand-in replies "2". Click **Check inbox now**: **BOOKED**, and the invite with the Meet link
   appears on the stand-in's phone (30 s).

**Close with:** "Every claim had a receipt, and the meeting is real."

**Fallbacks:**
- If a reply is misread, use the NEEDS_HUMAN buttons.
- If Crustdata is slow, the data shown is already the pre-run's.
- If the LLM hits the Max limit, set `LLM_BACKEND=anthropic_api` and restart.

## 11. Tier 2 (only after Tier 1 integration passes) and Tier 3 (not today)

- **Tier 2:**
  - P1: the LIVE consent form, the red LIVE badge, and an "Attach to contact" action for Unmatched messages.
  - P3: the proposed-time path, and the LIVE checks exercised end to end.
  - P2: the honest shortfall label in the funnel.
- **Tier 3, recorded in `TODOS.md`:** follow-ups and the demo clock, REPLAY of Crustdata responses, ICP
  editing, URL intake, Meet transcripts and meeting prep, Slack alerts, warm intros and social connections,
  and a backtest on past data.

## 12. Kickoff prompts (paste into your own Claude Code after `git pull`)

**P1 (Rithvik):**
```text
You are P1 on team Kingslayers. Read PLAN.md fully; it is the contract and wins over every other doc.
You own: app/__init__.py, app/config.py, app/db.py, app/models.py, app/journal.py, app/main.py,
app/static/index.html, requirements.txt, .env.example, README.md. Edit nothing else.
First (by 14:15): commit requirements.txt and the skeleton (config, db, models exactly per §5, journal,
main with / and /api/health) and push. Then build every route in §7, the background inbox loop, and the
UI in §8 against the contracts in §6 (stub calls locally until P2/P3 push; don't commit stubs).
Push every 10 minutes with git pull --rebase. Don't add features not in PLAN.md.
```

**P2 (discovery):**
```text
You are P2 on team Kingslayers. Read PLAN.md fully; it is the contract and wins over every other doc.
You own: app/llm.py, app/crustdata.py, app/scoring.py, app/discovery.py, app/drafting.py,
scripts/smoke_crustdata.py, tests/test_scoring.py, tests/test_claim_gate.py, docs/notes/crustdata-rest.md.
Edit nothing else. First (by 14:15): verify Crustdata request/response field names from
https://docs.crustdata.com plus one tiny real call per endpoint, record them in docs/notes/crustdata-rest.md,
note the real business-email status values, and push. Never guess a field name. Then build §6.1-§6.5 and
the P2 tests. Use DISCOVERY_COMPANY_LIMIT=5 while developing. Push every 10 minutes with git pull --rebase.
Don't add features not in PLAN.md.
```

**P3 (conversation):**
```text
You are P3 on team Kingslayers. Read PLAN.md fully; it is the contract and wins over every other doc.
You own: app/gates.py, app/mail.py, app/calendar_io.py, app/outreach.py, app/inbox.py, app/booking.py,
scripts/smoke_composio.py, tests/test_guard.py, tests/test_inbox.py, docs/notes/composio-tools.md.
Edit nothing else. First (by 14:15): with the Composio SDK, verify tool slugs and argument names, send one
email to STAND_IN_EMAIL, read the thread back, query free slots, and create one calendar event with a Meet
link for STAND_IN_EMAIL. If no Meet link comes back, apply the GOOGLEMEET_CREATE_MEET fallback in §6.8.
Record findings in docs/notes/composio-tools.md and push. Then build §6.6-§6.11 and the P3 tests; the
recipient guard is the safety core and fails closed. Push every 10 minutes with git pull --rebase.
Don't add features not in PLAN.md.
```

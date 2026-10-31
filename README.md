# Kingslayers

Our team repo for **ContextCon 03** (Crustdata, IIT Bombay). It's a sales agent where **every claim has a
receipt**: it finds real companies through live Crustdata, writes emails that cite their sources, reads
replies, and books a real Google Calendar meeting with a Meet link.

**Building? Read [`PLAN.md`](PLAN.md) first.** It's the contract, and it wins over every other doc.

## Setup (each teammate, once)

1. `git clone https://github.com/Rithvik-B/Kingslayers.git && cd Kingslayers`
2. `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
3. `cp .env.example .env`, then fill in the values Rithvik shares privately. Never set `ANTHROPIC_API_KEY`.
4. Run `claude` and trust the folder. You must be logged in to your own Claude Max account; the app's LLM
   calls use that login.
5. Run `/sync`, then paste your kickoff prompt from `PLAN.md` §12.

## Run the app

`.venv/bin/uvicorn app.main:app --port 8000`, then open http://localhost:8000. Tests:
`.venv/bin/pytest -q`.

The UI walks through: create a campaign → Generate ICP (saved to Seller Memory; Approve, Regenerate or Edit)
→ Run discovery on live Crustdata → ranked prospects with `[src]` receipts → open the ⭐ featured draft →
Send (goes to the stand-in inbox) → Check inbox now → slots offered → BOOKED with a Meet link. The
**Memory** tab shows and edits everything the agent believes and decided.

## What works (updated during integration)

- P1 foundation: models, Seller Memory with tests, every API route, one-page UI.
- P2 and P3: see their notes in `docs/notes/` once pushed.

## How we work

| When | Do |
|---|---|
| Starting a session | A hook shows whether you're behind origin, plus the decisions and ideas. Run `/sync` if you're behind. |
| The team settles something | `/decide <what we decided>` writes it to `docs/decisions/` and pushes it. |
| You have an idea | Ask Claude to write it up in `docs/ideas/` using the template. |
| You learn something useful | Ask Claude to add it to `docs/notes/`. |
| Stopping or switching tasks | `/handoff` updates `docs/STATUS.md`, catches unrecorded decisions, and pushes. |

The rules every Claude follows are in [`CLAUDE.md`](CLAUDE.md). The plan right now is in
[`docs/STATUS.md`](docs/STATUS.md).

Put personal preferences for your own Claude in `CLAUDE.local.md` or `.claude/settings.local.json`. Both are
gitignored.

## Layout

```
PLAN.md               the build contract: stack, ownership, module contracts, demo
TODOS.md              deferred work (not built today)
app/                  the FastAPI app and its one-page UI (see PLAN.md §3)
CLAUDE.md             shared instructions, loaded by every teammate's Claude
docs/STATUS.md        live board: phase, owners, next steps, open questions
docs/reference/       old specs, reference only (PLAN.md wins)
docs/assets/          the approved wireframe
docs/decisions/       one file per decision
docs/ideas/           one file per idea, with a scoring rubric
docs/notes/           research and lessons learned
competition-info/     organizer material: themes, past winners
.claude/              shared hook and the /sync, /decide, /handoff commands
.mcp.json             Crustdata MCP server (research in Claude Code only; the app uses REST)
```

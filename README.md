# Kingslayers

Our team repo for **ContextCon 03** (Crustdata, IIT Bombay). We each build with our own Claude Code, and this
repo is the shared memory that keeps all of them in sync.

## Setup (each teammate, once)

1. `git clone https://github.com/Rithvik-B/Kingslayers.git && cd Kingslayers`
2. Run `claude`. When it asks, trust the folder and approve the `crustdata` MCP server from `.mcp.json`.
3. In Claude, run `/mcp`, pick `crustdata` and log in.
4. `cp .env.example .env`, and fill in keys once we need them.
5. Run `/sync`, then add yourself to the Team table in `docs/STATUS.md`.

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
CLAUDE.md             shared instructions, loaded by every teammate's Claude
docs/STATUS.md        live board: phase, owners, next steps, open questions
docs/decisions/       one file per decision
docs/ideas/           one file per idea, with a scoring rubric
docs/notes/           research and lessons learned
competition-info/     organizer material: themes, past winners
.claude/              shared hook and the /sync, /decide, /handoff commands
.mcp.json             Crustdata MCP server
```

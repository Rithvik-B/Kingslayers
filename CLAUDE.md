# Kingslayers: ContextCon 03 (IIT Bombay) hackathon

This is a team repo. Each teammate runs their own Claude Code on it, so **the repo is the team's shared
memory**. Anything a teammate or their Claude would need to know goes in the repo. Your personal
auto-memory and the chat are not shared with anyone.

## Building? `PLAN.md` is the contract

**We are in the build.** `PLAN.md` at the repo root defines the stack, the file ownership (P1, P2, P3), every
module's contract, the routes, the UI and the demo. It wins over every other doc, including
`docs/reference/`.
- Build only what `PLAN.md` lists.
- Edit only the files your person owns (`PLAN.md` §3).
- Never substitute the stack: FastAPI + one HTML page, Crustdata REST, Composio for Gmail and Calendar,
  Claude via the Agent SDK.
- If a contract seems wrong, tell your user rather than working around it.

## Current state

@docs/STATUS.md

## The competition, in short

- Crustdata runs it. We build on Crustdata's people and company data: 800M+ profiles and 200M+ companies,
  with employment history, headcount over time, funding, hiring, job postings, posts, work emails, and live
  web search. The Crustdata MCP server is set up in `.mcp.json`.
- Brief: build an agent that replaces "any service people are paid to do, on data about people and
  companies." There are 10 themes: Hiring, Investing, Research and markets, Insurance, Trust and compliance,
  Buying and paying, Agents that spend, Supply chain, Revenue, and Infrastructure for agents. Or bring your
  own idea. Full text: `competition-info/themes.md`.
- Each theme ends with a "We're looking for" line that says how entries will be judged. Most mean testing on
  real past data, for example "tested on last year's real job openings" or "calls that hold up when tested
  on past dates, using only what was known on each date". Plan the evaluation or backtest from the start,
  not at the end.
- Past editions (`competition-info/contextcon-winning-submissions.md`): every placed entry put Crustdata
  data in front of a non-technical user at the moment they make a decision. The judges are founders and
  rewarded the problem over the stack. Most entries were generic recruiting, sales or VC-scouting tools, and
  those mostly did not place. Edition 2 used a 3-minute live demo plus 2 minutes of questions.

## Where things live

| Path | What |
|---|---|
| `PLAN.md` | **The build contract.** Stack, ownership, module contracts, routes, UI, demo. Wins over everything. |
| `TODOS.md` | Deferred work. Do not build it today. |
| `docs/reference/` | The old BUILD_SPEC and long spec. Reference only, for the sections `PLAN.md` cites. |
| `docs/STATUS.md` | Live board: phase, who is on what, next steps, open questions. Keep it current. |
| `docs/decisions/` | One file per team decision. Format and rules: `docs/decisions/README.md`. |
| `docs/ideas/` | One file per idea while we pick what to build. Template and scoring: `docs/ideas/README.md`. |
| `docs/notes/` | Research and lessons learned: API quirks, credit costs, what worked and what didn't. One file per topic. |
| `competition-info/` | Organizer material. Reference only, don't edit. |

## Rules for every Claude on this team

1. **Start in sync.** A SessionStart hook (`.claude/hooks/session-start.sh`) prints git sync state plus the
   lists of decisions and ideas. If the branch is behind origin, tell the user and offer `/sync` before
   doing any work.
2. **Follow accepted decisions.** Check `docs/decisions/` before proposing anything about the idea, scope,
   stack or design. Never contradict an accepted decision silently. If one looks wrong, say why and propose
   a new decision that replaces it.
3. **Record decisions as they happen** with `/decide`. A decision is anything a teammate would otherwise have
   to ask about: the idea, scope, stack, APIs, data model, who owns which area, the demo script, or a cut
   feature. If the user settles something and doesn't run `/decide`, offer to record it.
4. **Team facts go in the repo, not in auto-memory.** Use personal memory only for your own user's
   preferences. Put research in `docs/notes/`, decisions in `docs/decisions/`, and plans in
   `docs/STATUS.md`.
5. **Don't edit what someone else owns.** Before editing an area, check "Team" in `docs/STATUS.md`. If
   another teammate owns that area, tell the user.
6. **Hand off.** At the end of a work block, or when the user is about to stop, run or suggest `/handoff`
   so that STATUS.md shows what was done and what comes next.
7. **Git.** Pull before starting work. Make small commits. Run `git pull --rebase` before `git push`. Never
   force-push `main`. Push doc-only changes (decisions, ideas, notes, STATUS.md) right away so teammates see
   them; the team agreed to this in the first decision. During the build, commit and push your own files at
   least every 10 minutes, as `PLAN.md` §4 says. Otherwise, commit and push code only when the user asks.
8. **Secrets** go in `.env`, which is gitignored. `.env.example` lists the variable names and never holds
   values.

## Team commands

- `/sync`: pull and summarize what teammates changed
- `/decide <what was decided>`: record a decision, then commit and push it
- `/handoff`: update STATUS.md, record any unrecorded decisions, then commit and push

## Code

- **Run:** `.venv/bin/uvicorn app.main:app --port 8000`. **Test:** `.venv/bin/pytest -q`.
- **Layout and owners:** `PLAN.md` §3.
- **The app's LLM calls use the developer's Claude Max login** through the Agent SDK. Never set
  `ANTHROPIC_API_KEY`. In the app, always pass `setting_sources=[]`, so this file and the repo's hooks don't
  load into its LLM calls.
- **STAND_IN is the default delivery mode.** The recipient guard in `app/mail.py` must fail closed.

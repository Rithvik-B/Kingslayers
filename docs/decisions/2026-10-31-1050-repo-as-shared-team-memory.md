---
title: The repo is the team's shared memory; decisions are logged in docs/decisions and pushed right away
status: accepted
date: 2026-10-31
decided_by: Rithvik
---

## Context
Each teammate uses their own Claude Code on their own computer. Claude's auto-memory and chat history stay
on that one machine. Without a shared record, each Claude would work from different assumptions about the
idea, the stack and who is doing what.

## Decision
- `CLAUDE.md` is the shared instruction file. It pulls in `docs/STATUS.md`, so every session starts with the
  current plan.
- Every team decision gets its own file in `docs/decisions/`, created with `/decide`.
- `docs/STATUS.md` is the live board: phase, owners, next steps and open questions. `/handoff` keeps it up
  to date.
- Each idea gets its own file in `docs/ideas/`. Research and lessons learned go in `docs/notes/`.
- Doc-only changes (decisions, ideas, notes, STATUS.md) are committed and pushed right away. Code is
  committed and pushed when its owner asks.
- A SessionStart hook fetches from origin, then prints how far behind or ahead the branch is, along with the
  decisions and ideas, so a Claude that is out of date notices before it starts work.
- The Crustdata MCP server is set up in `.mcp.json`, so every teammate gets the same tools.

## Why
Shared context is in the repo, so it moves with every `git pull`. One file per decision or idea avoids merge
conflicts when several Claudes write at once. Pushing docs right away keeps the delay between a decision and
a teammate seeing it short.

## Alternatives considered
- One shared `DECISIONS.md`: simpler, but concurrent appends would conflict all the time.
- A shared Google Doc or Notion page: Claude Code doesn't read it automatically, so it would go out of date.
- Each person's Claude auto-memory: it isn't shared.

## Consequences
- Each teammate needs to run `/sync` at the start of a session (the hook reminds them) and `/handoff` at the
  end.
- Every teammate has to authenticate Crustdata once with `/mcp`.

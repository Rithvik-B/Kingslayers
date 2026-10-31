---
title: Build exactly PLAN.md, with FastAPI and one HTML page, Crustdata REST, Composio for Gmail and Calendar, and Claude via the Agent SDK on Max
status: accepted
date: 2026-10-31
decided_by: Rithvik
---

## Context
The deadline is 15:10 today. Three teammates, each with their own Claude Max account and Claude Code, build
in parallel. The design (`docs/reference/BUILD_SPEC.md`) assumed direct Google OAuth, Next.js and "any LLM
provider". In this session we chose otherwise. Without one contract, the three Claudes would build
different things.

## Decision
- **`PLAN.md` at the repo root is the build contract.** It wins over every other doc. Nobody builds anything
  outside it, and only a file's owner edits it (P1 Rithvik: app shell, routes, UI; P2: discovery and
  drafting; P3: sending, inbox and booking).
- **Stack:**
  - Python FastAPI with SQLite.
  - One HTML page served by FastAPI. No Next.js.
  - Crustdata **REST** API. Not the skills or MCP.
  - **Composio** for Gmail and Google Calendar. No Google OAuth client of our own.
  - Replies read by **polling** threads every 15 s plus a "Check inbox now" button. No triggers, webhooks
    or tunnel.
  - **Claude through the Agent SDK** on each developer's own Max login, with an Anthropic API key as backup
    behind the same adapter.
- **Demo:** runs on Rithvik's laptop in STAND_IN mode. Real discovery, but only one email delivered, to the
  stand-in inbox.
- **Scope:** Tier 1 (the stage path) first. Tier 2 only if integration passes. Tier 3 goes in `TODOS.md`.

## Why
Composio skips the Google Cloud OAuth setup that the deadline leaves no time for. Polling avoids Composio's
2-minute trigger delay and the need for a public URL. One HTML page needs no second server or build step.
Fixed contracts and strict file ownership let three Claudes merge without conflicts.

## Alternatives considered
- Direct Google APIs, from BUILD_SPEC: give full control over event ids, but the OAuth client and Meet test
  don't fit the remaining time.
- Next.js: slower, and needs someone fast at it.
- Crustdata skills through the Agent SDK: their output is chat text and files, so they can't produce the
  raw-record receipts our wedge depends on.

## Consequences
- **Supersedes** `2026-10-31-1351-demo-llm-on-claude-max.md`. The Max decision stands, but there's no tunnel
  now.
- **Risk:** Composio may not return a Meet link for a personal Gmail. P3 tests this first, and the fallback
  is a `GOOGLEMEET_CREATE_MEET` link (`PLAN.md` §6.8). BOOKED still requires an event id and a real Meet
  link.
- **No double-booking by event id:** without our own event ids, a description marker
  (`[kingslayers-mtg:<id>]`) prevents double bookings instead.
- **Moved to `docs/reference/`:** BUILD_SPEC.md and LONG_SPEC.md, with "reference only" banners. The old
  kickoff prompt and a duplicate copy of the long spec were deleted.

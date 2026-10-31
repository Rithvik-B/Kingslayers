---
title: The demo's LLM is Claude through the Agent SDK on Rithvik's Claude Max subscription, with the backend on his laptop
status: superseded by 2026-10-31-1425-final-build-plan-and-stack.md
date: 2026-10-31
decided_by: Rithvik
---

## Context
The backend runs the Crustdata skills and coordinates the agents through the Claude Agent SDK, which needs
Claude. The options were an Anthropic API key, the AIML API, or Rithvik's existing Claude Max subscription.
The app is only for the hackathon demo. It isn't commercial, and nobody outside the team uses it.

## Decision
- The demo uses Claude through the Agent SDK, authenticated with Rithvik's Claude Max login. We don't use
  the AIML API.
- The backend runs on **Rithvik's laptop**, logged in to Claude as him, not on a cloud server. A cloudflared
  tunnel gives Composio a public URL for its webhooks.
- `ANTHROPIC_API_KEY` must **not** be set on that machine. If it is, it takes priority and the usage is billed
  to the API.
- Slow research (ICP Builder, Sales Prospecting, Account Research) runs before the demo and is stored, so the
  demo doesn't use up the Max quota.
- We keep a backup Anthropic API key ready for demo day.

## Why
Anthropic's terms allow ordinary individual use of the Agent SDK on a Max plan. Usage draws from the plan's
limits. A demo-only app, run by its own developer, falls within that. It costs nothing extra and needs no
second LLM provider.

## Alternatives considered
- AIML API: its Anthropic-format endpoint isn't documented as working with the Agent SDK, and it lists older
  models.
- An Anthropic API key from the start: cleaner, but costs money we don't need to spend for a demo.

## Consequences
- **If the app is ever used by anyone else or goes commercial, switch to a Console API key.** Anthropic
  doesn't allow routing other users' requests through a Max plan. See
  `docs/notes/crustdata-skills-and-agent-sdk.md`.
- The demo depends on Rithvik's laptop and his quota, which is shared with his own Claude Code use. Watch the
  5-hour limit on demo day.
- Teammates build with their own Claude Code accounts. Only the demo backend uses Rithvik's login.
- Anthropic's policy has changed several times in 2026, so re-check it before the event.

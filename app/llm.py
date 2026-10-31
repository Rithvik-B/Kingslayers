"""LLM adapter (P2, PLAN.md §6.1).

complete_json(system, prompt, schema) -> dict, through one of two backends chosen by S.LLM_BACKEND:
  - agent_sdk:     Claude via the Claude Agent SDK on the developer's Claude Max login. No tools,
                   setting_sources=[] so this repo's CLAUDE.md and hooks never load into app calls.
  - anthropic_api: the backup, anthropic.AsyncAnthropic with BACKUP_ANTHROPIC_API_KEY; one forced tool whose
                   input_schema is the schema, and we return its input.
Every call retries once, then raises LLMError.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from app.config import S

log = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when the model gives no usable JSON after one retry, or the environment is unsafe."""


# Each agent_sdk call starts a `claude` process; keep at most 4 in flight.
_SEM = asyncio.Semaphore(4)


def _guard_env() -> None:
    # An API key in the environment overrides the Max login and bills the API instead.
    if "ANTHROPIC_API_KEY" in os.environ:
        raise LLMError("unset ANTHROPIC_API_KEY: it overrides the Max login")


async def _agent_sdk(system: str, prompt: str, schema: dict) -> dict:
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

    options = ClaudeAgentOptions(
        system_prompt=system,
        model=S.LLM_MODEL,
        output_format={"type": "json_schema", "schema": schema},
        max_turns=3,
        tools=[],            # no built-in tools at all
        allowed_tools=[],
        setting_sources=[],  # mandatory: keeps the repo's CLAUDE.md and hooks out of app calls
    )
    result: ResultMessage | None = None
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            result = message
    if result is None:
        raise LLMError("agent_sdk: no result message")
    if result.is_error or result.subtype != "success":
        raise LLMError(f"agent_sdk: {result.subtype}: {result.result or result.errors}")
    out = result.structured_output
    if not isinstance(out, dict):
        raise LLMError(f"agent_sdk: no structured_output (got {type(out).__name__})")
    return out


async def _anthropic_api(system: str, prompt: str, schema: dict) -> dict:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=S.BACKUP_ANTHROPIC_API_KEY)
    resp = await client.messages.create(
        model=S.BACKUP_ANTHROPIC_MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        tools=[{"name": "emit", "description": "Return the answer as JSON matching the schema.",
                "input_schema": schema}],
        tool_choice={"type": "tool", "name": "emit"},
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and isinstance(block.input, dict):
            return block.input
    raise LLMError("anthropic_api: no tool_use block in the response")


async def complete_json(system: str, prompt: str, schema: dict) -> dict:
    """One structured LLM call. Returns a dict matching `schema`, or raises LLMError."""
    backend = (S.LLM_BACKEND or "agent_sdk").strip().lower()
    if backend == "agent_sdk":
        _guard_env()
        fn = _agent_sdk
    elif backend == "anthropic_api":
        fn = _anthropic_api
    else:
        raise LLMError(f"unknown LLM_BACKEND {backend!r}")

    last: Exception | None = None
    for attempt in (1, 2):
        try:
            async with _SEM:
                return await fn(system, prompt, schema)
        except LLMError as e:
            last = e
        except Exception as e:  # SDK/process/network errors
            last = e
        log.warning("llm attempt %d failed (%s): %s", attempt, backend, last)
        if attempt == 1:
            await asyncio.sleep(1.0)
    raise LLMError(f"{backend}: failed twice: {last}") from last

# Crustdata skills plugin, and running it from our app with the Claude Agent SDK

2026-10-31, Rithvik (via Claude). From the Crustdata docs, the plugin's GitHub repo, and the Agent SDK docs.
Sources are at the bottom.

## What the plugin is

- **It's a Claude Code plugin made of prompt-driven skills, not a REST API.** The skills call Crustdata
  through the Crustdata MCP server (`https://install.crustdata.com/mcp`, which runs JavaScript via `execute`
  and `callTool`).
- **Repo:** `github.com/crustdata/skills`, MIT license, so we may copy and modify it.
- **Install in Claude Code:** `claude plugin marketplace add crustdata/skills`, then
  `claude plugin install crustdata@crustdata-plugin`.
- **Auth:** run `/crustdata:login`. `CRUSTDATA_API_KEY` in the environment takes precedence over the saved
  login.
- **Shared config:** `icp-builder` writes `config/persona-profile.md` and `config/gtm-config.md` in the
  working directory. `sales-prospecting`, `account-research`, `sales-outreach` and `meeting-prep` read those
  files.

## What each skill does

| Skill | Input | What it gives | Notes |
|---|---|---|---|
| `icp-builder` | The **seller's own** LinkedIn URL | ICP, persona and writing voice, saved to `config/` | Run once per seller. The ICP is always labeled "inferred". |
| `sales-prospecting` | ICP | New target lists, lookalikes, account ranking, market sizing, champion tracking | This is the step that **finds** prospect companies. |
| `account-research` | A company | Account plan, org chart, tech stack and angle, battlecard | Deep dive on companies already chosen. |
| `warm-path-workspace` | An account | Buying-group map, stakeholder dossiers, live signals, warm-intro paths | |
| `social-connections` | A person's LinkedIn URL | People that person **plausibly** knows, graded A–D, as an xlsx file plus `final.json` | Inferred from overlapping jobs and schools and from post engagement. **Not** real LinkedIn connections. Engagement data is often missing. |
| `email-enrichment` | Email lists or people | Profiles, verified emails and phones | Can resume long runs. |
| `sales-outreach` | Person, account or a signal | Cold email (under 90 words, 2–3 variants), sequences, replies, objection answers | **Drafts only. Never sends.** Opens on a dated signal (post within 60 days, company event within 90 days, job posting, or prospecting signal) and never invents one. Contact email via `person_contact_enrich` (opt-in, costs credits). |
| `meeting-prep` | Inbound leads or a meeting | Inbound lead scores, pre-call brief, discovery and demo plan | |
| `candidate-sourcing` | A role | Recruiting, not sales | |

Credit costs mentioned in the skills: `person_enrich` 1, `company_enrich` 2 per match, `social_post_list_live`
1 per post. `company_identify` and the autocomplete calls are free.

## Running the skills from a backend (Claude Agent SDK)

- **Loading the plugin:** pass `plugins=[{"type": "local", "path": "<plugin dir>"}]`. Only local paths work;
  there's no marketplace install in the SDK. Invoke a skill by sending `/crustdata:<skill> <args>` as the
  prompt.
- **Loading our own skills:** set `setting_sources` to include `"project"`, and set `cwd`. If you pass an
  explicit tools list, include `"Skill"`.
- **Remote MCP:** use `{"type": "http", "url": ..., "headers": {...}}`. The SDK does **not** run OAuth, so
  pass a token or API key ourselves (the plugin honours `CRUSTDATA_API_KEY`).
- **JSON output:** `output_format={"type": "json_schema", "schema": ...}`, then read `structured_output`. The
  schema must be JSON Schema draft-07.
- **Each `query()` starts a `claude` CLI subprocess.** Plan for about 1 GiB of RAM per concurrent session.
  Set `max_turns`, since sessions have no timeout.
- **One `cwd` per seller or campaign.** The skills write files (`config/`, run folders, xlsx and CSV)
  relative to it.
- **Cost figures:** `total_cost_usd` is the SDK's own estimate, not what we're billed.

## Running headless: auth and LLM endpoint (checked 2026-10-31)

- **The plugin's `.mcp.json` has no auth.** It is only `{"type": "http", "url": "https://install.crustdata.com/mcp"}`
  and relies on the browser login.
- **The Crustdata MCP server takes an API key headlessly** as `Authorization: Bearer <CRUSTDATA_API_KEY>`
  (per the MCP docs). In the Agent SDK, define the `crustdata` MCP server ourselves with that header.
  - **Untested:** whether the plugin's skills then use our server.
  - **Fallback:** fork the plugin and add the header to its `.mcp.json`.
- **The Agent SDK needs an endpoint in Anthropic Messages format.**
  - AIML API documents `POST https://api.aimlapi.com/v1/messages` (Anthropic format, with tools) alongside
    its OpenAI-compatible `/v1/chat/completions`.
  - The Claude models listed for `/v1/messages` are the 4.x family (for example `claude-sonnet-4-6`,
    `claude-opus-4-7`).
  - Claude Code and the Agent SDK aren't documented as working with it. **Untested:**
    `ANTHROPIC_BASE_URL=https://api.aimlapi.com`, plus the right auth variable and model ID.
  - **Fallback:** a direct Anthropic API key for the Agent SDK, and AIML only for simple one-shot LLM calls.

## Running the Agent SDK on a Claude Max subscription instead of an API key (checked 2026-10-31)

- **Allowed:** ordinary, individual use. Claude Code's legal page says plan limits "assume ordinary,
  individual usage of Claude Code and the Agent SDK". The Help Center says Agent SDK and `claude -p` usage
  draw from the subscription's limits. The separate monthly Agent SDK credit announced for June 15 is
  **paused**.
- **Not allowed:** a product that other people use. The terms say developers "should use API key
  authentication", and Anthropic does not permit "route requests through Free, Pro, Max, or Ultra plan
  credentials on behalf of their users", nor offering Claude.ai login inside our app.
- **What this means for us:**
  - Building with Claude Code on Max is fine.
  - Running the backend on our own laptop, logged in as ourselves, for development and our own demo counts
    as individual use.
  - Once anyone else uses the app, it needs a Console API key.
  - Don't put a personal subscription token on a shared cloud server.
- **Practical points:**
  - The backend's agent runs share one quota with that person's interactive Claude Code use. If the 5-hour
    limit runs out mid-demo, the agent stops. Run research ahead of time and keep a backup API key.
  - If `ANTHROPIC_API_KEY` is set in the environment, it takes priority and is billed to the API instead.
- **This policy has changed several times in 2026.** Re-check the two pages below before the event.

## Sources

- https://code.claude.com/docs/en/legal-and-compliance (authentication and credential use)
- https://code.claude.com/docs/en/agent-sdk/overview (note on claude.ai login)
- https://support.claude.com/en/articles/15036540 (Agent SDK with your Claude plan)
- https://docs.crustdata.com/for-agents/mcp
- https://docs.aimlapi.com/api-references/text-models-llm/anthropic
- https://docs.crustdata.com/integrations/claude-plugin
- https://github.com/crustdata/skills (skills/icp-builder, skills/social-connections, skills/sales-outreach SKILL.md)
- https://code.claude.com/docs/en/agent-sdk/plugins.md
- https://code.claude.com/docs/en/agent-sdk/skills.md
- https://code.claude.com/docs/en/agent-sdk/mcp.md
- https://code.claude.com/docs/en/agent-sdk/structured-outputs.md
- https://code.claude.com/docs/en/agent-sdk/hosting.md

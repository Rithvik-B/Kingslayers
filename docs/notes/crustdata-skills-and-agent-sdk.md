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

## Sources

- https://docs.crustdata.com/integrations/claude-plugin
- https://github.com/crustdata/skills (skills/icp-builder, skills/social-connections, skills/sales-outreach SKILL.md)
- https://code.claude.com/docs/en/agent-sdk/plugins.md
- https://code.claude.com/docs/en/agent-sdk/skills.md
- https://code.claude.com/docs/en/agent-sdk/mcp.md
- https://code.claude.com/docs/en/agent-sdk/structured-outputs.md
- https://code.claude.com/docs/en/agent-sdk/hosting.md

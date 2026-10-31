> **For the build** (see `PLAN.md`): we use Composio tools but **no triggers or webhooks**; replies are read by polling threads every 15 s.

# Composio with Gmail, Google Calendar, Google Meet and Slack

2026-10-31, Rithvik (via Claude). Checked against the Composio and Google docs on that date. Re-check limits
before relying on them. Sources are at the bottom.

## Connecting a user's accounts

- **Concepts:**
  - Auth config: one per toolkit, created in the Composio dashboard.
  - `user_id`: our own ID for the seller.
  - Connected account: one seller's login for one toolkit.
- **Connect flow:** call `composio.connected_accounts.link(user_id, auth_config_id, callback_url)` and
  redirect the user to the `redirect_url` it returns. Composio holds the tokens; we store only the `user_id`.
- **Don't use `initiate()` with Composio-managed OAuth.** Composio is retiring it. New organizations get a
  400 error from 2026-05-08, and all organizations from 2026-07-03. Older tutorials and LLM-written code
  still use it.
- **Composio-managed OAuth** is fine for development and a hackathon. Production needs our own OAuth client.
  Google apps in test mode or unverified can have refresh tokens expire, which forces the user to consent
  again.
- **Connection status:** only `ACTIVE` connections can run tools. Disabling an account also disables its
  triggers, and re-enabling the account does **not** turn the triggers back on.

## Receiving events (triggers)

- **Register a webhook** with `composio.triggers.set_webhook_subscription(webhook_url=...)`. Keep the
  `secret` it returns.
- **Verify and parse** each event with
  `composio.triggers.parse(body=raw_body, headers=..., verify_secret=...)`. The event metadata contains
  `user_id`, `connected_account_id`, `trigger_slug` and `trigger_id`.
- **Local development:** run
  `composio dev triggers listen --forward http://localhost:8000/webhooks/composio`, or a cloudflared or ngrok
  tunnel.
- **The Gmail new-message trigger polls the inbox.**
  - With Composio-managed auth, the minimum interval is 2 minutes, per the current troubleshooting page.
    Older preview docs said 15 minutes.
  - A new message can take a full interval to appear.
  - The first poll sets a baseline, and earlier messages are never delivered.
- **Avoid reply loops:** skip events sent from the connected mailbox or its send-as aliases. Creating
  `GMAIL_EMAIL_SENT_TRIGGER` does not stop our own messages from appearing as new-message events.
- **Demo workaround:** while waiting on specific threads, fetch just those threads with the Gmail tools every
  15–20 seconds. Keep the trigger as the background path.

## Google Calendar

- **`GOOGLECALENDAR_CREATE_EVENT`:**
  - `create_meeting_room` adds a Meet link and is on by default.
  - `attendees` sets who is invited.
  - `send_updates` is `all`, `externalOnly` or `none`. The default is `all`, so attendees get the invite by
    email, Meet link included.
  - Composio's docs say **personal Gmail accounts fall back to an event with no Meet link**. Test this.
- **Finding a time:** `GOOGLECALENDAR_FIND_FREE_SLOTS` returns computed free slots;
  `GOOGLECALENDAR_FREE_BUSY_QUERY` returns raw busy intervals.

## Google Meet: recording and transcripts

- **No triggers.** Composio's `googlemeet` toolkit has 25 tools and no triggers, so we poll for the transcript
  after the meeting's end time.
- **Getting a transcript takes three calls:**
  1. `GOOGLEMEET_LIST_CONFERENCE_RECORDS`, filtered by meeting code, space or time range
  2. `GOOGLEMEET_GET_TRANSCRIPTS_BY_CONFERENCE_RECORD_ID`
  3. `GOOGLEMEET_LIST_TRANSCRIPT_ENTRIES`, which returns entries with speaker, time and text
- **Gemini notes:** `GOOGLEMEET_LIST_SMART_NOTES` returns metadata only; the note content comes from the Docs
  API.
- **Timing:** transcripts appear minutes after the meeting ends, so an empty result may only mean "not yet".
- **Turning transcription on automatically:**
  - The Meet API setting is `config.artifactConfig.transcriptionConfig.autoTranscriptionGeneration`, with
    `recordingConfig.autoRecordingGeneration` for recording.
  - `GOOGLEMEET_CREATE_MEET` accepts this config, but Composio doesn't document the field names, and settings
    it doesn't support may be ignored without an error.
  - A space created by `GOOGLEMEET_CREATE_MEET` is not attached to a calendar event.
  - The fallback is for the organizer to switch transcription on by hand once the meeting starts.
- **Google plan requirement** (the organizer's account):
  - **Transcripts:** Business Standard or Plus, Enterprise Starter, Standard or Plus, Teaching and Learning
    Upgrade, Education Plus, or Workspace Individual.
  - **Recording:** Business Standard or Plus, Essentials, Enterprise Essentials or Plus, or Education Plus.
    A Workspace admin must also turn recording on.
  - **Free personal Gmail gets neither.**
  - We need the transcript, not the video recording.

## Sources

- https://docs.composio.dev/docs/authenticating-tools
- https://docs.composio.dev/docs/setting-up-triggers/subscribing-to-events
- https://docs.composio.dev/docs/setting-up-triggers/troubleshooting
- https://docs.composio.dev/toolkits/googlecalendar
- https://docs.composio.dev/toolkits/googlemeet
- https://support.google.com/meet/answer/12849897 (transcripts by edition)
- https://support.google.com/meet/answer/9308681 (recording by edition)
- https://developers.google.com/meet/api/reference/rest/v2/spaces (artifactConfig)

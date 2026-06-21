# Slack setup (Socket Mode — no public URL required)

Warden uses Socket Mode, so you don't need ngrok or a public endpoint. ~5 minutes.

1. Go to <https://api.slack.com/apps> → **Create New App** → **From an app manifest**.
2. Pick your workspace, then paste the manifest below.
3. **Install to Workspace** and copy the **Bot User OAuth Token** (`xoxb-…`)
   → `SLACK_BOT_TOKEN` in `.env`.
4. **Basic Information → App-Level Tokens → Generate** a token with the
   `connections:write` scope. Copy it (`xapp-…`) → `SLACK_APP_TOKEN` in `.env`.
5. Invite the bot to a channel: `/invite @warden`.
6. `docker compose up --build`, then just talk to Warden in that channel:
   `@warden can you triage the issues on owner/repo?`. Warden is conversational —
   it figures out which capability you mean, asks a clarifying question if you
   leave something out (e.g. the repo), and follows the rest of the thread without
   needing another @mention.

## App manifest

```yaml
display_information:
  name: Warden
  description: Triage agent with a permission ledger
  background_color: "#0b0d10"
features:
  bot_user:
    display_name: warden
    always_online: true
oauth_config:
  scopes:
    bot:
      - app_mentions:read   # hear @warden …
      - chat:write          # post proposals + results
      - channels:history    # follow thread replies in public channels
      - groups:history      # …and private channels
      # - im:history        # uncomment to also converse in DMs
      # - mpim:history
settings:
  event_subscriptions:
    bot_events:
      - app_mention
      - message.channels    # follow-up replies (public channels)
      - message.groups      # …and private channels
      # - message.im        # uncomment for DMs
      # - message.mpim
  interactivity:
    is_enabled: true        # the Approve / Deny buttons
  socket_mode_enabled: true
  org_deploy_enabled: false
```

Notes
- Warden never touches GitHub through Slack — GitHub access is the agent's
  read-only token and the runner's write token, both separate from Slack.
- The `*.history` scopes + `message.*` events are what let Warden follow a thread
  conversationally after the first @mention. Drop them if you'd rather it only
  respond to explicit @mentions.
- Interactivity is enabled for Socket Mode (button clicks arrive over the socket;
  no request URL needed).

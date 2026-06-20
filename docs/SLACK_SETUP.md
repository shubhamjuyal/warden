# Slack setup (Socket Mode — no public URL required)

Warden uses Socket Mode, so you don't need ngrok or a public endpoint. ~5 minutes.

1. Go to <https://api.slack.com/apps> → **Create New App** → **From an app manifest**.
2. Pick your workspace, then paste the manifest below.
3. **Install to Workspace** and copy the **Bot User OAuth Token** (`xoxb-…`)
   → `SLACK_BOT_TOKEN` in `.env`.
4. **Basic Information → App-Level Tokens → Generate** a token with the
   `connections:write` scope. Copy it (`xapp-…`) → `SLACK_APP_TOKEN` in `.env`.
5. Invite the bot to a channel: `/invite @warden`.
6. `docker compose up --build`, then in that channel invoke any capability:
   `@warden <capability> <subject>` — e.g. `@warden triage owner/repo`. The bot
   lists available capabilities if you `@warden` it with no arguments.

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
settings:
  event_subscriptions:
    bot_events:
      - app_mention
  interactivity:
    is_enabled: true        # the Approve / Deny buttons
  socket_mode_enabled: true
  org_deploy_enabled: false
```

Notes
- The bot only needs `chat:write` and `app_mentions:read`. It never touches
  GitHub through Slack — GitHub access is the agent's read-only token and the
  runner's write token, both separate from Slack.
- Interactivity is enabled for Socket Mode (button clicks arrive over the socket;
  no request URL needed).

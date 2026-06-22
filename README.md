# LookArr 🎬

> ⚠️ **Transparency & Disclaimer**
>
> I wanted a tool like [plexannouncer](https://github.com/tenasi/plexannouncer) but felt some settings and the Discord embed design were lacking. Since I have no coding knowledge, I had [Claude](https://claude.ai) (Anthropic's AI) build and extend this fork entirely.
>
> **I have not manually reviewed the code myself.** Use this project at your own risk.
>
> This tool handles sensitive data (Plex tokens, Discord webhook URLs). It is intended for use **within your local home network**. Exposing it to the internet is done **at your own risk** — see the Security section below for the mitigations that are in place and their limits.

A Discord bot that announces newly added Plex media with rich embeds — large posters, ratings, genres, and more.

> Based on [plexannouncer](https://github.com/tenasi/plexannouncer) by tenasi. Extended with improved Discord embed design, additional metadata, security hardening, Unraid support, and YAML configuration.

---

## Features

- 🎬 **New Movies** – large poster, description, runtime, rating, genre, director
- 📺 **New Shows** – large poster, description, season count, genre
- ▶️ **New Episodes** – S01E01 format, runtime, description, new season detection
- 🎵 **New Music** – artist, album, duration
- 🔒 **Security:** IP whitelist, rate limiting, User-Agent filter, payload validation

---

## What's different from the original?

| Area | Original `plexannouncer` | LookArr |
|---|---|---|
| Poster | Small thumbnail (right side) | **Large poster image** (full width) |
| Embed color | Plex gold for everything | Different color per media type |
| Movie fields | Title, summary, duration, year, rating | + genres, director, audience rating, formatted runtime |
| Show fields | Title, summary, year, rating | + season count, episode count, genres |
| Episode format | `Show: Episode Title` with `Season: 1` / `Episode: 5` | `Show · S01E05 – Episode Title` + new season detection |
| Discord webhooks | Single webhook URL | **Multiple webhooks** (list) |
| Library filter | – | Filter announcements by Plex library (`ALLOWED_LIBRARIES`) |
| Discord library | `RequestsWebhookAdapter` (removed in discord.py 2.0) | Modern `SyncWebhook` API |
| Configuration | JSON | **YAML** with inline comments |
| Security | Token in URL only | **IP whitelist, rate limit, User-Agent filter, payload validation, X-Forwarded-For support** |
| Testing | – | **Test message at startup + `/test/<token>` endpoint** |
| Unraid | – | **Community Applications XML template** |
| Build | – | GitHub Actions → `ghcr.io` |
| Error handling | Crashes on malformed payloads | Logged and skipped, server keeps running |

---

## Setup on Unraid

### 1. Create a Discord Webhook

1. Open your Discord server
2. Channel Settings (⚙️) → **Integrations** → **Webhooks** → **New Webhook**
3. Copy the webhook URL

### 2. Add the Container

**Docker tab → "Add Container":**

| Field | Value |
|---|---|
| Repository | `ghcr.io/mlo-tek/lookarr:latest` |
| Port | Host `32500` → Container `32500` (TCP) |
| Volume | `/mnt/user/appdata/lookarr` → `/config` |

### 3. Set Environment Variables

| Variable | Required | Description |
|---|---|---|
| `PLEX_SERVER_URL` | ✅ | Your Plex server URL |
| `PLEX_WEBHOOK_TOKEN` | ✅ | A random token of your choice (becomes part of the webhook URL) |
| `DISCORD_WEBHOOK_URLS` | ✅ | Discord webhook URL(s), comma-separated for multiple |
| `PLEX_TOKEN` | ➖ | Your personal Plex token (optional) |
| `ALLOWED_LIBRARIES` | ➖ | Comma-separated library names to announce, empty = all |
| `ALLOWED_IPS` | ➖ | **Recommended.** Comma-separated IPs/networks allowed to send webhooks. Empty = all allowed |
| `RATE_LIMIT_MAX` | ➖ | Max requests per IP per window (default `60`) |
| `RATE_LIMIT_WINDOW` | ➖ | Rate limit window in seconds (default `60`) |
| `REQUIRE_PLEX_USER_AGENT` | ➖ | Reject requests whose User-Agent isn't Plex (`true`/`false`, default `true`) |
| `SEND_TEST_MESSAGE` | ➖ | Send a test message to all Discord webhooks at container start (`true`/`false`, default `false`) |
| `LOGLEVEL` | ➖ | `DEBUG`, `INFO`, `WARNING` (default `INFO`) |

**Alternatively use a config.yaml** at `/mnt/user/appdata/lookarr/config.yaml`:

```yaml
plex_server_url: "https://app.plex.tv/desktop#!/server/YOUR_SERVER_ID"
plex_webhook_token: "some-random-token"
discord_webhook_urls:
  - "https://discord.com/api/webhooks/WEBHOOK_ID/WEBHOOK_TOKEN"
allowed_libraries: []
allowed_ips:
  - "192.168.1.50"        # your Plex server
  - "192.168.1.0/24"      # your LAN
rate_limit_max: 60
rate_limit_window: 60
require_plex_user_agent: true
```

### 4. Register the Webhook in Plex

Plex → **Settings** → **Webhooks** → **Add Webhook**:
```
http://UNRAID-IP:32500/YOUR_TOKEN
```

---

## Testing the connection

You can verify that LookArr can reach your Discord channel in two ways:

### Option A: Test message at startup

Set `SEND_TEST_MESSAGE=true` (or `send_test_message: true` in `config.yaml`) and restart the container. On startup, LookArr will send a test embed to all configured Discord webhooks. After confirming it works, set the value back to `false`.

### Option B: Trigger a test message on demand

LookArr exposes a separate test endpoint:

```
GET http://UNRAID-IP:32500/test/YOUR_TOKEN
```

Open this URL in your browser (or `curl` it). LookArr will send a test message to every configured Discord webhook and return a JSON status with which ones succeeded and which failed. This works at any time, no restart needed.

The test endpoint respects the same IP whitelist and rate limit as the main webhook endpoint, so it is **not publicly callable** when you've configured `ALLOWED_IPS`.

---

## Security

**Plex webhooks have no HMAC/signature mechanism.** There is no way to cryptographically verify that an incoming webhook actually came from your Plex server. LookArr therefore stacks several lighter checks:

| Layer | What it does | Limits |
|---|---|---|
| Token in URL | Caller must know the secret token in the URL path | Anyone who learns the URL can call it |
| **IP whitelist** | Only accepts requests from configured IPs/networks | TCP makes IP spoofing very hard, so this is the strongest layer |
| Rate limiting | Limits requests per IP per time window | Mitigates spam/flooding |
| User-Agent filter | Rejects requests not claiming `PlexMediaServer/...` | Easily spoofed, just an extra hurdle |
| Payload validation | Rejects malformed JSON or non-Plex payloads | Bad payloads can still trigger the bot if they look right |

### Recommendations

- **Keep it on your LAN.** Don't expose it to the internet unless you have a reason.
- **Always set `ALLOWED_IPS`** when exposed. List only the IP of your Plex server (and maybe your reverse proxy / Tailscale network). This is the single most effective protection.
- **Use a reverse proxy with TLS** if you expose it externally. LookArr itself only serves HTTP.
- **Use a long, random `PLEX_WEBHOOK_TOKEN`** (32+ characters). It's the only thing protecting the URL itself.
- **Use a separate Discord channel** for these notifications so a flood of fake webhooks would only spam that channel.

### What is NOT protected

- A successful intruder with shell access to your server can read the config file (Plex token, Discord webhook URLs in plain text).
- A reverse-proxy misconfiguration that strips `X-Forwarded-For` can break the IP whitelist.
- Discord webhook URLs in your config are themselves capable of posting to your channel — treat them like passwords.

---

## Finding your Plex Token

1. Open Plex Web
2. Click any movie → `···` → **View XML**
3. In the URL: `X-Plex-Token=XXXXXXXXXX` — that's your token

---

## Credits

Based on [tenasi/plexannouncer](https://github.com/tenasi/plexannouncer) – MIT License

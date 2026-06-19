# Postiz — self-hosted scheduler (the posting last-mile)

Open-source (AGPL-3.0) alternative to Buffer/Metricool. Runs locally via Docker and
publishes our rendered MP4s to YouTube, TikTok, and Instagram. We never upload footage —
only the brand-original videos the pipeline renders.

- UI: **http://localhost:4007**
- Public API base: `http://localhost:4007/api/public/v1` (self-hosted proxies the backend
  under `/api`; the bare `/public/v1` path hits the frontend and 307s to `/auth`). Used by
  `pipeline/publish.py`.
- Stack: Postiz + Postgres + Redis + a Temporal workflow stack (Temporal + its own
  Postgres + Elasticsearch). It's heavy (~6 containers, a few GB RAM) but all local + free.

## Run it

```bash
cd deploy/postiz
docker compose up -d          # first run pulls several GB
docker compose ps             # wait until 'postiz' is healthy (start_period ~120s)
docker compose logs -f postiz # watch boot / migrations
```

Stop / reset:
```bash
docker compose down           # stop (keeps data)
docker compose down -v        # stop + wipe volumes (fresh start)
```

The `JWT_SECRET` in `docker-compose.yaml` was generated locally for this install. URLs are
pinned to `localhost:4007`. `DISABLE_REGISTRATION: 'false'` lets you create the first account.

## First-time account

1. Open http://localhost:4007 and register (use the project email).
2. After creating the org, you'll add channels (next section).

## Connect YouTube (OAuth — the interactive part)

YouTube publishing needs a Google Cloud OAuth app. You do this once:

1. **Google Cloud Console** → create/select a project.
2. **APIs & Services → Library** → enable **YouTube Data API v3**.
3. **OAuth consent screen** → External; **add the channel's Google account under "Test
   users"** (keeps it in "Testing", no Google review needed for your own channel). The YouTube
   scopes are *sensitive/restricted*, so Google blocks any account that isn't an explicit test
   user — see the 403 note below. Scopes: Postiz requests the YouTube upload/read scopes during
   connect.
4. **Credentials → Create credentials → OAuth client ID → Web application**.
   - Authorized JavaScript origins: **`http://localhost:4007`** (no path / trailing slash).
   - Authorized redirect URI: **`http://localhost:4007/integrations/social/youtube`**
     (Postiz's YouTube callback. If connect fails with redirect_uri_mismatch, copy the exact
     URI from the error and add it here.)
5. Copy the **Client ID** and **Client secret** into `docker-compose.yaml`:
   ```yaml
   YOUTUBE_CLIENT_ID: '...'
   YOUTUBE_CLIENT_SECRET: '...'
   ```
   then `docker compose down && docker compose up -d` (recreates the postiz container with the
   new env).
6. In the Postiz UI → **add a channel → YouTube** → complete the Google consent → your
   channel appears as a connected integration. At the **"Google hasn't verified this app"**
   screen, click **Advanced → Go to (app) (unsafe) → Continue** — expected for an unverified
   personal app.

### Gotcha: `Error 403: access_denied` on connect
The app is in **Testing** and the Google account you picked isn't a **Test user**. Fix: add
that exact Gmail under OAuth consent screen → **Test users**, and make sure the Google account
chooser uses the same account (multiple signed-in accounts → picking the wrong one re-triggers
the 403).

### Gotcha: connection breaks ~weekly (7-day refresh-token expiry)
While the OAuth app stays in **Testing**, Google **expires the refresh token after 7 days** —
so the Postiz↔YouTube link silently dies about once a week and you must reconnect (a ~10s
click in the Postiz UI). To make it unattended, **Publish app** on the OAuth consent screen
(Testing → Production): refresh tokens then don't expire. For a single-owner app posting to
your own channel you can proceed through the unverified-app warning; full Google verification
is only truly required if you onboard *other people's* accounts. Recommendation: stay in
Testing while proving the pipeline, switch to Production before relying on scheduled posting.

> TikTok and Instagram work the same way (their own `*_CLIENT_ID/SECRET` in the compose +
> a developer app). Add them once YouTube is proven end-to-end.

### Gotcha: post fires but fails with `ECONNREFUSED 127.0.0.1:4007`
The app listens on **:5000** inside the container; media URLs are built from `FRONTEND_URL`
(**:4007**), which only exists as the host→container publish. So the background worker, when
it fetches the uploaded MP4 to push to YouTube, hits `127.0.0.1:4007` *inside* the container
and is refused. Fix (already in `docker-compose.yaml`): the **`postiz-loopback`** sidecar —
an `alpine/socat` container sharing Postiz's network namespace (`network_mode:
service:postiz`) that forwards internal `:4007 → :5000`. Keeps the public port + OAuth redirect
at 4007 unchanged. If you ever change the public port, update both the socat `command` and the
URLs together.

## Publish a rendered video

1. Postiz UI → **Settings → Developers → Public API** → copy the API key.
2. Add it to the repo `.env` (gitignored):
   ```
   POSTIZ_API_KEY=...
   ```
3. Find your channel's integration id:
   ```bash
   uv run pipeline/publish.py channels
   ```
4. Schedule (or post now) a rendered MP4 with its spec's caption/title/hashtags:
   ```bash
   # post immediately
   uv run pipeline/publish.py publish \
     out/specs/lionel-messi-last-dance.json \
     out/renders/lionel-messi-last-dance.mp4 \
     --integration <id> --platform youtube --when now

   # or schedule
   uv run pipeline/publish.py publish out/specs/<spec>.json out/renders/<video>.mp4 \
     --integration <id> --platform youtube --when 2026-06-20T15:00:00.000Z
   ```

`publish.py` uploads the MP4, then creates the post — for YouTube it sets the title from
`youtube_title`, the description from `youtube_description`, hashtags as tags, and marks it a
Short. Caption selection is per-platform (`tiktok_caption` / `instagram_caption`). On a
successful publish/schedule it also **moves the render to `out/published/`**.

## Scheduled posts failing? (token expiry — the #1 cause)

The most common failure: the YouTube OAuth token has gone invalid, so queued posts error at
publish time (`state=ERROR`). Root cause is almost always the **Testing-mode 7-day
refresh-token expiry** — fix permanently by publishing the Google OAuth app to **Production**.

**Diagnose before trusting a schedule:**
```bash
# worker error logs
docker compose logs postiz --since 24h | grep -iE "invalid credentials|invalid_token|authError"
# integration + post state (DB)
docker compose exec -T postiz-postgres psql -U postiz-user -d postiz-db-local \
  -c 'SELECT name,"refreshNeeded",disabled,"tokenExpiration" FROM "Integration" WHERE "deletedAt" IS NULL;'
docker compose exec -T postiz-postgres psql -U postiz-user -d postiz-db-local \
  -c 'SELECT state,"publishDate",substring(content,1,30) FROM "Post" ORDER BY "createdAt" DESC LIMIT 8;'
```
Tokens are stored **plaintext** in `Integration.token`/`refreshToken`. To prove the refresh
path works *right now*, POST the refresh token + `YOUTUBE_CLIENT_ID/SECRET` to
`https://oauth2.googleapis.com/token` (`grant_type=refresh_token`) — `access_token` returned =
healthy. If it's dead, **reconnect the channel** in the UI (re-runs OAuth, issues a fresh token).

## Security

- `docker-compose.yaml` holds a local-only `JWT_SECRET` and (once you add them) OAuth
  secrets. Treat it as a secret file — don't push real OAuth credentials to a public remote.
- `POSTIZ_API_KEY` lives in `.env`, which is gitignored. Never commit it.

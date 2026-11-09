# Telegram Music Bot

An aiogram 3 bot served through a Flask webhook. It keeps the existing CAPTCHA, mandatory channel membership check, RU/EN language preference, Apple catalog search, preview delivery, and SQLite user data.

Search results come from Apple's public iTunes Search API. The bot sends the available preview clips directly in Telegram; it does not include music website links or fetch full recordings. Song-editing handlers are not present in the current source.

## Deploy to Render

1. Create a Render Web Service from the repository.
2. Set the build command to:

   ```bash
   pip install -r requirements.txt
   ```

3. Set the start command to:

   ```bash
   gunicorn --bind 0.0.0.0:$PORT flask_app:application
   ```

4. Add these environment variables in the Render dashboard:
   - `TELEGRAM_BOT_TOKEN`
   - `REQUIRED_CHANNELS`
   - `REQUIRED_CHANNEL_LINKS` if any required channels are private
   - `WEBHOOK_SECRET` optionally; if omitted, the app derives one from the bot token

Render provides `RENDER_EXTERNAL_URL` automatically. On startup, `flask_app.py` passes `os.environ["RENDER_EXTERNAL_URL"]` to the bot runtime, which calls Telegram's `set_webhook` with that exact URL. The Flask app receives updates at `/` and forwards them to aiogram. Do not set a separate `WEBHOOK_URL`.

The app also exposes `GET /` as a health check. In the Replit preview, where `RENDER_EXTERNAL_URL` is not set, the server starts in health-only mode; webhook POSTs return `503`. The bot runtime starts on Render when Render supplies the URL.

## Run locally

From the repository root:

```bash
uv sync
cp telegram_music_bot/.env.example telegram_music_bot/.env
# Set TELEGRAM_BOT_TOKEN and REQUIRED_CHANNELS in telegram_music_bot/.env.
PYTHONPATH=telegram_music_bot/src python -m music_bot
```

For local webhook processing, also set `RENDER_EXTERNAL_URL` to a public HTTPS URL that Telegram can reach. Without it, local mode only serves the health check.

## SQLite persistence

`DATABASE_PATH` defaults to `data/music_bot.sqlite3` under the repository root. The directory is created automatically. Render's default filesystem is ephemeral, so SQLite changes can be lost on a restart or deploy. Render persistent disks are available only for paid services. If user verification and language preferences must persist on Render, mount a persistent disk and set `DATABASE_PATH` to a location under that mount.

## Files used by Render

- `flask_app.py`
- `requirements.txt`
- The complete `telegram_music_bot/` directory, including `src/music_bot/`
- `data/music_bot.sqlite3` only if migrating existing user records; store it on persistent storage if it must survive redeploys

Do not commit or upload a file containing the bot token. Set secrets in Render's environment-variable settings.

## Configuration

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot token from BotFather |
| `REQUIRED_CHANNELS` | Yes | — | Comma-separated public handles or chat IDs |
| `REQUIRED_CHANNEL_LINKS` | No | Derived for public handles | Invite links aligned with channel IDs |
| `DATABASE_PATH` | No | `data/music_bot.sqlite3` | SQLite database path |
| `SEARCH_RESULTS_LIMIT` | No | `50` | Catalog results to paginate (1–200) |
| `CAPTCHA_TTL_SECONDS` | No | `300` | Time allowed to solve a CAPTCHA |
| `ITUNES_COUNTRY` | No | `US` | Two-letter iTunes storefront |
| `RENDER_EXTERNAL_URL` | Yes on Render | Provided by Render | HTTPS webhook URL |
| `WEBHOOK_SECRET` | No | Derived from the bot token | Optional Telegram webhook secret |

Channel membership is rechecked before each search. Telegram Bot API calls and music search require outbound HTTPS access.

# Telegram Music Bot

An aiogram 3 bot served through a Flask webhook. It keeps the existing CAPTCHA, mandatory channel membership check, RU/EN language preference, Apple catalog search, preview delivery, and SQLite user data.

Search results come from Apple's public iTunes Search API. The bot sends the available preview clips directly in Telegram; it does not include music website links or fetch full recordings. Song-editing handlers are not present in the current source.

## Run locally

From the repository root:

```bash
uv sync
cp telegram_music_bot/.env.example telegram_music_bot/.env
# Set TELEGRAM_BOT_TOKEN and REQUIRED_CHANNELS in telegram_music_bot/.env.
PYTHONPATH=telegram_music_bot/src python -m music_bot
```

The local Flask server listens on `PORT` (default `5000`). On startup it calls `set_webhook` for `WEBHOOK_URL`, which defaults to:

```text
https://basirbizurtanov.pythonanywhere.com/
```

## Deploy to PythonAnywhere

1. Upload `flask_app.py`, `requirements.txt`, and the full `telegram_music_bot/` directory to a folder under your PythonAnywhere home directory.
2. Create a Python 3.11+ virtual environment for the web app and install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy `telegram_music_bot/.env.example` to `telegram_music_bot/.env` on PythonAnywhere. Set `TELEGRAM_BOT_TOKEN`, `REQUIRED_CHANNELS`, and any private-channel invite links there. Keep this file private; it is loaded as environment variables and should not be committed.
4. In the PythonAnywhere **Web** tab, configure the web app to use the same Python version and virtual environment. Edit its WSGI configuration file to add the project folder to `sys.path` and import the WSGI application:

   ```python
   import sys

   project_folder = "/home/basirbizurtanov/your-project-folder"
   if project_folder not in sys.path:
       sys.path.insert(0, project_folder)

   from flask_app import application
   ```

5. Set the web app domain to `basirbizurtanov.pythonanywhere.com` and reload it. Importing `flask_app.py` initializes the bot and registers the webhook at the configured URL.

The webhook endpoint accepts Telegram `POST` updates at `/`. Requests are checked with Telegram's `X-Telegram-Bot-Api-Secret-Token` header. If `WEBHOOK_SECRET` is omitted, the app derives a secret from the bot token. `GET /` is a small health check.

**PythonAnywhere free-tier limitation:** PythonAnywhere restricts outbound internet access for free accounts. Its current allowlist includes `.apple.com` but does not list `api.telegram.org`, which this bot needs to register the webhook and send replies. Request that documented Telegram Bot API domain be allowlisted before using the free tier, or host the bot somewhere with unrestricted outbound HTTPS. Without outbound access to Telegram, the webhook app cannot operate.

`DATABASE_PATH` defaults to `data/music_bot.sqlite3` under the project folder. The directory is created automatically. To keep existing verified users and language preferences when moving hosts, copy the current `data/music_bot.sqlite3` file to the same relative location on PythonAnywhere before the first request.

## Files to upload

- `flask_app.py`
- `requirements.txt`
- The complete `telegram_music_bot/` directory, including `src/music_bot/`
- The existing `data/music_bot.sqlite3` only if you need to preserve stored users and language preferences

Create the real `telegram_music_bot/.env` on PythonAnywhere after upload; do not upload or share a file containing the bot token.

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
| `WEBHOOK_URL` | No | `https://basirbizurtanov.pythonanywhere.com/` | Public HTTPS URL registered with Telegram |
| `WEBHOOK_SECRET` | No | Derived from the bot token | Optional Telegram webhook secret |

Channel membership is rechecked before each search. Telegram Bot API calls and music search still require outbound HTTPS access from the hosting account.

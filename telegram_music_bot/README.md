# Telegram Music Bot

An aiogram 3 bot that verifies users with a short arithmetic CAPTCHA, checks required channel membership, and searches songs by title or artist.

Search results come from Apple's public iTunes Search API. Selecting a song shows Listen and Website buttons. Listen downloads and sends Apple's short preview directly in Telegram; the website remains available as a fallback. The bot does not download full recordings.

On first use, users choose English or Russian. They can change the saved preference with `/language`. CAPTCHA answers can be selected from inline buttons or typed as a number.

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and save its token as the `TELEGRAM_BOT_TOKEN` Replit Secret.
2. Add the bot as an administrator to each required channel. Telegram only guarantees `getChatMember` results for other users when the bot is an administrator.
3. Set `REQUIRED_CHANNELS` to a comma-separated list of public channel handles or Telegram chat IDs:
   - Public channels: `@music_news,@another_channel`
   - Private channels: `-1001234567890`
4. For private channels, set `REQUIRED_CHANNEL_LINKS` to comma-separated invite links in the same order as `REQUIRED_CHANNELS`. Public channel links are derived automatically.
5. Start the **Telegram Music Bot** workflow.

The workflow reports a clear configuration error if required channels or the bot token are missing.

## Run locally

From the repository root:

```bash
uv sync
cp telegram_music_bot/.env.example telegram_music_bot/.env
# Fill in the values in telegram_music_bot/.env, then:
set -a
source telegram_music_bot/.env
set +a
PYTHONPATH=telegram_music_bot/src python -m music_bot
```

Never commit `.env` or paste the bot token into source code.

## Configuration

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Yes | — | Token from BotFather |
| `REQUIRED_CHANNELS` | Yes | — | Comma-separated public handles or chat IDs |
| `REQUIRED_CHANNEL_LINKS` | No | Derived for public handles | Comma-separated join links, aligned with channels |
| `DATABASE_PATH` | No | `data/music_bot.sqlite3` | SQLite file for CAPTCHA-verified user IDs |
| `SEARCH_RESULTS_LIMIT` | No | `5` | Results per search (1–10) |
| `CAPTCHA_TTL_SECONDS` | No | `300` | Time allowed to solve a CAPTCHA |
| `ITUNES_COUNTRY` | No | `US` | Two-letter iTunes search storefront |

CAPTCHA verification is persisted in SQLite. Channel membership is checked again before every search, so users who leave a required channel lose access until they rejoin.

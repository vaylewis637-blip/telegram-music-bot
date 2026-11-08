# Telegram Music Bot

An aiogram 3 Telegram bot that verifies new users, enforces required channel subscriptions, and searches Apple's public music catalog by song title or artist.

## Run & Operate

- `pnpm --filter @workspace/api-server run dev` — run the API server (port 5000)
- `PYTHONPATH=telegram_music_bot/src python -m music_bot` — run the Telegram bot
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- Required bot env: `TELEGRAM_BOT_TOKEN`, `REQUIRED_CHANNELS`
- Optional bot env: `REQUIRED_CHANNEL_LINKS`, `DATABASE_PATH`, `SEARCH_RESULTS_LIMIT`, `CAPTCHA_TTL_SECONDS`, `ITUNES_COUNTRY`
- Existing API server env: `DATABASE_URL` — Postgres connection string

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9, Python 3.13
- API: Express 5
- DB: PostgreSQL + Drizzle ORM
- Validation: Zod (`zod/v4`), `drizzle-zod`
- API codegen: Orval (from OpenAPI spec)
- Build: esbuild (CJS bundle)
- Telegram bot: aiogram 3, aiohttp, SQLite

## Where things live

- `telegram_music_bot/src/music_bot/` — bot configuration, handlers, state, and services
- `telegram_music_bot/README.md` — BotFather setup, channel permissions, and local run instructions
- `lib/api-spec/openapi.yaml` — API contract for the existing API server
- `artifacts/mockup-sandbox/` — reusable design-preview tooling

## Architecture decisions

- The bot uses long polling and does not expose a web server.
- Music search uses Apple's public iTunes Search API and returns track/preview links rather than downloading full recordings.
- CAPTCHA verification is stored in SQLite; channel membership is checked again before each search.

## Product

- Users solve an arithmetic CAPTCHA, join configured channels, and search the public music catalog by title or artist.

## User preferences

- Keep the bot implementation in a clean, standalone Python package.

## Gotchas

- Add the bot as an administrator to every required channel so Telegram allows membership checks.
- Configure `REQUIRED_CHANNELS` before starting the bot; each private channel also needs a matching invite URL in `REQUIRED_CHANNEL_LINKS`.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details

from __future__ import annotations

import atexit
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

PROJECT_ROOT = Path(__file__).resolve().parent
BOT_SOURCE = PROJECT_ROOT / "telegram_music_bot" / "src"
sys.path.insert(0, str(BOT_SOURCE))

# Load local development variables; Render injects its environment variables.
load_dotenv(PROJECT_ROOT / "telegram_music_bot" / ".env", override=False)

database_path = Path(
    os.getenv("DATABASE_PATH", "data/music_bot.sqlite3")
).expanduser()
if not database_path.is_absolute():
    database_path = PROJECT_ROOT / database_path
os.environ["DATABASE_PATH"] = str(database_path.resolve())

from music_bot.webhook import (  # noqa: E402
    TelegramWebhookRuntime,
    create_flask_app,
)

runtime: TelegramWebhookRuntime | None = None
if "RENDER_EXTERNAL_URL" in os.environ:
    runtime = TelegramWebhookRuntime(
        webhook_url=os.environ["RENDER_EXTERNAL_URL"],
    )
elif os.getenv("REPL_ID"):
    logging.getLogger(__name__).warning(
        "RENDER_EXTERNAL_URL is missing; webhook processing is disabled in this preview."
    )
else:
    raise RuntimeError(
        "RENDER_EXTERNAL_URL must be set by Render before starting the bot."
    )

app: Flask = create_flask_app(runtime, runtime.secret_token if runtime else "")
application = app
if runtime is not None:
    atexit.register(runtime.close)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        use_reloader=False,
    )

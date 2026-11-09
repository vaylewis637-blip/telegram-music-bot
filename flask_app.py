from __future__ import annotations

import atexit
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

PROJECT_ROOT = Path(__file__).resolve().parent
BOT_SOURCE = PROJECT_ROOT / "telegram_music_bot" / "src"
sys.path.insert(0, str(BOT_SOURCE))

# PythonAnywhere does not automatically load a project's .env file into WSGI.
load_dotenv(PROJECT_ROOT / "telegram_music_bot" / ".env", override=False)

database_path = Path(
    os.getenv("DATABASE_PATH", "data/music_bot.sqlite3")
).expanduser()
if not database_path.is_absolute():
    database_path = PROJECT_ROOT / database_path
os.environ["DATABASE_PATH"] = str(database_path.resolve())

from music_bot.webhook import (  # noqa: E402
    DEFAULT_WEBHOOK_URL,
    TelegramWebhookRuntime,
    create_flask_app,
)

runtime = TelegramWebhookRuntime(
    webhook_url=os.getenv("WEBHOOK_URL", DEFAULT_WEBHOOK_URL),
)
app: Flask = create_flask_app(runtime, runtime.secret_token)
application = app
atexit.register(runtime.close)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        use_reloader=False,
    )

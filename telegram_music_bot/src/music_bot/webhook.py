from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import re
import threading
from collections.abc import Mapping
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, Protocol
from urllib.parse import urlsplit

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from flask import Flask, jsonify, request
from pydantic import ValidationError

from music_bot.config import Settings
from music_bot.handlers.access import router as access_router
from music_bot.handlers.search import router as search_router
from music_bot.services.music_search import MusicSearch
from music_bot.services.preview_downloader import PreviewDownloader
from music_bot.services.user_repository import UserRepository

logger = logging.getLogger(__name__)

DEFAULT_WEBHOOK_URL = "https://basirbizurtanov.pythonanywhere.com/"
WEBHOOK_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
UPDATE_TIMEOUT_SECONDS = 55
WEBHOOK_SECRET_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


class UpdateProcessor(Protocol):
    def process_update(self, payload: Mapping[str, Any]) -> None: ...


class TelegramWebhookRuntime:
    """Owns aiogram's async runtime while serving synchronous WSGI requests."""

    def __init__(
        self,
        webhook_url: str | None = None,
        secret_token: str | None = None,
    ) -> None:
        self.settings = Settings.from_env()
        self.webhook_url = _validate_webhook_url(
            webhook_url or os.getenv("WEBHOOK_URL", DEFAULT_WEBHOOK_URL)
        )
        self.secret_token = _resolve_secret_token(
            self.settings.bot_token,
            secret_token or os.getenv("WEBHOOK_SECRET"),
        )

        self._loop = asyncio.new_event_loop()
        self._loop_ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run_event_loop,
            name="telegram-webhook-loop",
            daemon=True,
        )
        self._http_session: aiohttp.ClientSession | None = None
        self._bot: Bot | None = None
        self._dispatcher: Dispatcher | None = None
        self._update_lock: asyncio.Lock | None = None
        self._closed = False

        self._thread.start()
        if not self._loop_ready.wait(timeout=10):
            self.close()
            raise RuntimeError("The Telegram event loop did not start.")

        try:
            asyncio.run_coroutine_threadsafe(
                self._startup(),
                self._loop,
            ).result(timeout=60)
        except Exception:
            self.close()
            raise

    def _run_event_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop_ready.set()
        try:
            self._loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            self._loop.close()

    async def _startup(self) -> None:
        repository = UserRepository(self.settings.database_path)
        await repository.initialize()

        self._http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        )
        self._bot = Bot(
            token=self.settings.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self._dispatcher = Dispatcher(storage=MemoryStorage())
        self._dispatcher["settings"] = self.settings
        self._dispatcher["repository"] = repository
        self._dispatcher["music_search"] = MusicSearch(
            session=self._http_session,
            country=self.settings.itunes_country,
        )
        self._dispatcher["preview_downloader"] = PreviewDownloader(
            self._http_session
        )
        self._dispatcher.include_routers(access_router, search_router)
        self._update_lock = asyncio.Lock()

        await self._bot.set_webhook(
            url=self.webhook_url,
            secret_token=self.secret_token,
            allowed_updates=self._dispatcher.resolve_used_update_types(),
        )
        logger.info("Telegram webhook configured at %s", self.webhook_url)

    async def _feed_update(self, payload: Mapping[str, Any]) -> None:
        if self._bot is None or self._dispatcher is None or self._update_lock is None:
            raise RuntimeError("The Telegram webhook runtime is not ready.")

        update = Update.model_validate(dict(payload), context={"bot": self._bot})
        async with self._update_lock:
            await self._dispatcher.feed_update(self._bot, update)

    def process_update(self, payload: Mapping[str, Any]) -> None:
        if self._closed or not self._loop.is_running():
            raise RuntimeError("The Telegram webhook runtime is not running.")
        future = asyncio.run_coroutine_threadsafe(
            self._feed_update(payload),
            self._loop,
        )
        future.result(timeout=UPDATE_TIMEOUT_SECONDS)

    async def _close_services(self) -> None:
        if self._http_session is not None and not self._http_session.closed:
            await self._http_session.close()
        if self._bot is not None:
            await self._bot.session.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    self._close_services(),
                    self._loop,
                ).result(timeout=10)
            except Exception:
                logger.debug("Could not close every Telegram client session", exc_info=True)
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread.is_alive():
            self._thread.join(timeout=10)


def create_flask_app(
    runtime: UpdateProcessor,
    secret_token: str,
) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024

    @app.get("/")
    def health_check():
        return jsonify({"ok": True, "service": "telegram-music-bot"}), 200

    @app.post("/")
    def receive_telegram_update():
        supplied_token = request.headers.get(WEBHOOK_SECRET_HEADER, "")
        if not hmac.compare_digest(supplied_token, secret_token):
            return jsonify({"ok": False, "error": "forbidden"}), 403

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid JSON update"}), 400

        try:
            runtime.process_update(payload)
        except ValidationError:
            app.logger.warning("Rejected an invalid Telegram update")
            return jsonify({"ok": False, "error": "invalid Telegram update"}), 400
        except FutureTimeoutError:
            app.logger.exception("Telegram update processing timed out")
            return jsonify({"ok": False, "error": "update processing timed out"}), 503
        except Exception:
            app.logger.exception("Telegram update processing failed")
            return jsonify({"ok": False, "error": "update processing failed"}), 500

        return jsonify({"ok": True}), 200

    return app


def _validate_webhook_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("WEBHOOK_URL must be an HTTPS URL.")
    return value


def _resolve_secret_token(bot_token: str, configured: str | None) -> str:
    if configured:
        if not WEBHOOK_SECRET_PATTERN.fullmatch(configured):
            raise ValueError(
                "WEBHOOK_SECRET must use only letters, numbers, underscores, "
                "or hyphens and be at most 256 characters."
            )
        return configured

    return hashlib.sha256(
        f"telegram-webhook:{bot_token}".encode("utf-8")
    ).hexdigest()

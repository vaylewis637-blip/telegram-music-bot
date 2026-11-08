from __future__ import annotations

import asyncio
import logging
import sys

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from music_bot.config import ConfigurationError, Settings
from music_bot.handlers.access import router as access_router
from music_bot.handlers.search import router as search_router
from music_bot.services.music_search import MusicSearch
from music_bot.services.preview_downloader import PreviewDownloader
from music_bot.services.user_repository import UserRepository

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = Settings.from_env()
    repository = UserRepository(settings.database_path)
    await repository.initialize()

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        bot = Bot(
            token=settings.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        dispatcher = Dispatcher(storage=MemoryStorage())
        dispatcher["settings"] = settings
        dispatcher["repository"] = repository
        dispatcher["music_search"] = MusicSearch(
            session=session,
            country=settings.itunes_country,
        )
        dispatcher["preview_downloader"] = PreviewDownloader(session)
        dispatcher.include_routers(access_router, search_router)

        try:
            logger.info(
                "Starting Telegram music bot with %d required channel(s)",
                len(settings.required_channels),
            )
            await dispatcher.start_polling(bot)
        finally:
            await bot.session.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run())
    except ConfigurationError as error:
        logger.error("Bot configuration error: %s", error)
        sys.exit(2)
    except KeyboardInterrupt:
        logger.info("Bot stopped")


if __name__ == "__main__":
    main()

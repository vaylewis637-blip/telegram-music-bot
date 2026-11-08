from __future__ import annotations

import html
import logging
from urllib.parse import urlparse

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from music_bot.config import Settings
from music_bot.handlers.access import require_access
from music_bot.i18n import translate
from music_bot.models import Track
from music_bot.services.music_search import MusicSearch, MusicSearchError
from music_bot.services.user_repository import UserRepository

router = Router(name="search")
logger = logging.getLogger(__name__)


@router.message(Command("search"))
async def handle_search_command(
    message: Message,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    repository: UserRepository,
    music_search: MusicSearch,
) -> None:
    if not await require_access(message, state, bot, settings, repository):
        return

    query = (message.text or "").partition(" ")[2].strip()
    if not query:
        language = await repository.get_language(
            message.from_user.id if message.from_user else 0
        )
        await message.answer(translate(language, "search_prompt"))
        return
    language = await repository.get_language(
        message.from_user.id if message.from_user else 0
    )
    await search_and_reply(message, query, settings, music_search, language or "en")


@router.message(F.text)
async def handle_text_search(
    message: Message,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    repository: UserRepository,
    music_search: MusicSearch,
) -> None:
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return
    if not await require_access(message, state, bot, settings, repository):
        return
    language = await repository.get_language(
        message.from_user.id if message.from_user else 0
    )
    await search_and_reply(message, text, settings, music_search, language or "en")


async def search_and_reply(
    message: Message,
    query: str,
    settings: Settings,
    music_search: MusicSearch,
    language: str = "en",
) -> None:
    status = await message.answer(translate(language, "searching"))
    try:
        tracks = await music_search.search(
            query=query,
            limit=settings.search_results_limit,
        )
    except MusicSearchError:
        logger.exception("Music catalog search failed")
        await status.edit_text(translate(language, "search_failed"))
        return

    if not tracks:
        await status.edit_text(
            translate(language, "no_tracks", query=html.escape(query))
        )
        return

    await status.edit_text(
        format_tracks(query, tracks, language),
        reply_markup=track_keyboard(tracks, language),
    )


def format_tracks(
    query: str,
    tracks: list[Track],
    language: str = "en",
) -> str:
    lines = [translate(language, "results_for", query=html.escape(query))]
    for index, track in enumerate(tracks, start=1):
        title = html.escape(track.title)
        artist = html.escape(track.artist)
        album = (
            html.escape(track.album)
            if track.album
            else translate(language, "album_unavailable")
        )
        lines.append(f"\n<b>{index}. {title}</b>\n{artist} · {album}")
    return "\n".join(lines)


def track_keyboard(
    tracks: list[Track],
    language: str = "en",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, track in enumerate(tracks, start=1):
        buttons = [
            InlineKeyboardButton(
                text=translate(language, "open_track", number=index),
                url=track.track_url,
            )
        ]
        if track.preview_url and _is_https_url(track.preview_url):
            buttons.append(
                InlineKeyboardButton(
                    text=translate(language, "preview_track", number=index),
                    url=track.preview_url,
                )
            )
        rows.append(buttons)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _is_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)

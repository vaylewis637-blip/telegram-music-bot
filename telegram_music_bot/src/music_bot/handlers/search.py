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
        await message.answer(
            "Send a song title or artist after the command, for example:\n"
            "<code>/search Daft Punk</code>"
        )
        return
    await search_and_reply(message, query, settings, music_search)


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
    await search_and_reply(message, text, settings, music_search)


async def search_and_reply(
    message: Message,
    query: str,
    settings: Settings,
    music_search: MusicSearch,
) -> None:
    status = await message.answer("Searching the music catalog…")
    try:
        tracks = await music_search.search(
            query=query,
            limit=settings.search_results_limit,
        )
    except MusicSearchError:
        logger.exception("Music catalog search failed")
        await status.edit_text(
            "The music catalog is temporarily unavailable. Please try again shortly."
        )
        return

    if not tracks:
        await status.edit_text(
            f"No tracks found for <b>{html.escape(query)}</b>. "
            "Try another title or artist."
        )
        return

    await status.edit_text(
        format_tracks(query, tracks),
        reply_markup=track_keyboard(tracks),
    )


def format_tracks(query: str, tracks: list[Track]) -> str:
    lines = [f"Results for <b>{html.escape(query)}</b>:"]
    for index, track in enumerate(tracks, start=1):
        title = html.escape(track.title)
        artist = html.escape(track.artist)
        album = html.escape(track.album) if track.album else "Album unavailable"
        lines.append(f"\n<b>{index}. {title}</b>\n{artist} · {album}")
    return "\n".join(lines)


def track_keyboard(tracks: list[Track]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, track in enumerate(tracks, start=1):
        buttons = [
            InlineKeyboardButton(
                text=f"Open track {index}",
                url=track.track_url,
            )
        ]
        if track.preview_url and _is_https_url(track.preview_url):
            buttons.append(
                InlineKeyboardButton(
                    text=f"Preview {index}",
                    url=track.preview_url,
                )
            )
        rows.append(buttons)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _is_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)

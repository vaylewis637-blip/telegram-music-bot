from __future__ import annotations

import html
import logging
import secrets
import time
from dataclasses import asdict

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from music_bot.config import Settings
from music_bot.handlers.access import require_access
from music_bot.i18n import translate
from music_bot.models import Track
from music_bot.services.music_search import MusicSearch, MusicSearchError
from music_bot.services.preview_downloader import (
    PreviewDownloadError,
    PreviewDownloader,
)
from music_bot.services.user_repository import UserRepository

router = Router(name="search")
logger = logging.getLogger(__name__)
SELECTION_TTL_SECONDS = 30 * 60
MAX_STORED_SEARCHES = 8


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
    await search_and_reply(
        message,
        query,
        settings,
        music_search,
        state,
        language or "en",
    )


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
    await search_and_reply(
        message,
        text,
        settings,
        music_search,
        state,
        language or "en",
    )


async def search_and_reply(
    message: Message,
    query: str,
    settings: Settings,
    music_search: MusicSearch,
    state: FSMContext,
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

    result_set_id = await store_track_results(state, tracks)
    await status.edit_text(
        format_tracks(query, tracks, language),
        reply_markup=track_keyboard(tracks, result_set_id, language),
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
    result_set_id: str,
    language: str = "en",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, track in enumerate(tracks, start=1):
        rows.append(
            [
                InlineKeyboardButton(
                    text=translate(
                        language,
                        "select_track",
                        title=_truncate_button_title(track.title),
                    ),
                    callback_data=f"song:{result_set_id}:{index}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def song_action_keyboard(
    track: Track,
    result_set_id: str,
    index: int,
    language: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "listen_button"),
                    callback_data=f"listen:{result_set_id}:{index}",
                ),
                InlineKeyboardButton(
                    text=translate(language, "website_button"),
                    url=track.track_url,
                ),
            ]
        ]
    )


def website_fallback_keyboard(
    track: Track,
    language: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "website_button"),
                    url=track.track_url,
                )
            ]
        ]
    )


@router.callback_query(F.data.startswith("song:"))
async def handle_song_selection(
    callback: CallbackQuery,
    state: FSMContext,
    repository: UserRepository,
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    parsed = _parse_result_callback(callback.data or "", "song")
    language = await repository.get_language(callback.from_user.id) or "en"
    if parsed is None:
        await callback.answer(translate(language, "selection_expired"), show_alert=True)
        return

    result_set_id, index = parsed
    track = await get_stored_track(state, result_set_id, index)
    if track is None:
        await callback.answer(translate(language, "selection_expired"), show_alert=True)
        return

    await callback.answer()
    await callback.message.answer(
        translate(
            language,
            "song_actions",
            title=html.escape(track.title),
        ),
        reply_markup=song_action_keyboard(
            track,
            result_set_id,
            index,
            language,
        ),
    )


@router.callback_query(F.data.startswith("listen:"))
async def handle_listen_selection(
    callback: CallbackQuery,
    state: FSMContext,
    repository: UserRepository,
    preview_downloader: PreviewDownloader,
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    parsed = _parse_result_callback(callback.data or "", "listen")
    language = await repository.get_language(callback.from_user.id) or "en"
    if parsed is None:
        await callback.answer(translate(language, "selection_expired"), show_alert=True)
        return

    result_set_id, index = parsed
    track = await get_stored_track(state, result_set_id, index)
    if track is None:
        await callback.answer(translate(language, "selection_expired"), show_alert=True)
        return

    await callback.answer()
    status = await callback.message.answer(
        translate(language, "downloading_preview")
    )
    if not track.preview_url:
        await status.edit_text(
            translate(language, "preview_unavailable"),
            reply_markup=website_fallback_keyboard(track, language),
        )
        return

    try:
        audio_data = await preview_downloader.download(track.preview_url)
    except PreviewDownloadError:
        logger.exception("Audio preview download failed")
        await status.edit_text(
            translate(language, "download_failed"),
            reply_markup=website_fallback_keyboard(track, language),
        )
        return

    filename = preview_downloader.filename_for(track.preview_url)
    caption = translate(
        language,
        "audio_caption",
        title=html.escape(track.title),
        artist=html.escape(track.artist),
    )
    try:
        await callback.message.answer_audio(
            audio=BufferedInputFile(audio_data, filename=filename),
            title=track.title,
            performer=track.artist,
            caption=caption,
        )
    except TelegramAPIError:
        logger.warning("Telegram audio upload failed; retrying as a document", exc_info=True)
        try:
            await callback.message.answer_document(
                document=BufferedInputFile(audio_data, filename=filename),
                caption=caption,
            )
        except TelegramAPIError:
            logger.exception("Telegram document upload failed")
            await status.edit_text(
                translate(language, "download_failed"),
                reply_markup=website_fallback_keyboard(track, language),
            )
            return

    try:
        await status.delete()
    except TelegramAPIError:
        logger.debug("Could not remove audio download status message")


async def store_track_results(
    state: FSMContext,
    tracks: list[Track],
) -> str:
    now = time.time()
    state_data = await state.get_data()
    stored_sets = state_data.get("song_search_sets", {})
    if not isinstance(stored_sets, dict):
        stored_sets = {}

    stored_sets = {
        key: value
        for key, value in stored_sets.items()
        if _is_recent_search(value, now)
    }
    result_set_id = secrets.token_hex(4)
    stored_sets[result_set_id] = {
        "created_at": now,
        "tracks": [asdict(track) for track in tracks],
    }
    while len(stored_sets) > MAX_STORED_SEARCHES:
        oldest_id = min(
            stored_sets,
            key=lambda key: float(stored_sets[key].get("created_at", 0)),
        )
        del stored_sets[oldest_id]
    await state.update_data(song_search_sets=stored_sets)
    return result_set_id


async def get_stored_track(
    state: FSMContext,
    result_set_id: str,
    index: int,
) -> Track | None:
    if index < 1:
        return None
    state_data = await state.get_data()
    stored_sets = state_data.get("song_search_sets", {})
    if not isinstance(stored_sets, dict):
        return None
    result_set = stored_sets.get(result_set_id)
    if not isinstance(result_set, dict):
        return None
    try:
        if time.time() - float(result_set["created_at"]) >= SELECTION_TTL_SECONDS:
            return None
        tracks = result_set["tracks"]
        track_data = tracks[index - 1]
        return Track(**track_data)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _parse_result_callback(
    data: str,
    action: str,
) -> tuple[str, int] | None:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != action:
        return None
    try:
        index = int(parts[2])
    except ValueError:
        return None
    return (parts[1], index) if index > 0 else None


def _truncate_button_title(title: str, limit: int = 42) -> str:
    normalized = " ".join(title.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _is_recent_search(value: object, now: float) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        return now - float(value.get("created_at", 0)) < SELECTION_TTL_SECONDS
    except (TypeError, ValueError):
        return False

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

MAX_BUTTONS_PER_PAGE = 5
SEARCH_STATE_TTL_SECONDS = 60 * 60


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
    language = await _language_for_message(message, repository)
    if not query:
        await message.answer(translate(language, "search_prompt"))
        return
    await search_and_reply(
        message,
        query,
        settings,
        music_search,
        state,
        language,
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
    query = (message.text or "").strip()
    if not query or query.startswith("/"):
        return
    if not await require_access(message, state, bot, settings, repository):
        return

    language = await _language_for_message(message, repository)
    await search_and_reply(
        message,
        query,
        settings,
        music_search,
        state,
        language,
    )


async def search_and_reply(
    message: Message,
    query: str,
    settings: Settings,
    music_search: MusicSearch,
    state: FSMContext,
    language: str = "en",
) -> None:
    await state.update_data(
        current_search_id=None,
        search_query=query,
        current_page=1,
        current_search_results=[],
        search_created_at=time.time(),
    )
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
            translate(language, "no_tracks", query=html.escape(_shorten(query, 120)))
        )
        return

    search_id = secrets.token_hex(4)
    await state.update_data(
        current_search_id=search_id,
        search_query=query,
        current_page=1,
        current_search_results=[asdict(track) for track in tracks],
        search_created_at=time.time(),
    )
    await render_result_page(
        status,
        state,
        language,
        search_id,
        requested_page=1,
    )


async def render_result_page(
    message: Message,
    state: FSMContext,
    language: str,
    search_id: str,
    requested_page: int | None = None,
) -> bool:
    search = await get_current_search(state, search_id)
    if search is None:
        return False

    tracks: list[Track] = search["tracks"]
    query: str = search["query"]
    page_ranges = _page_ranges(len(tracks))
    total_pages = len(page_ranges)
    page = requested_page if requested_page is not None else search["page"]
    if page < 1 or page > total_pages:
        return False

    await state.update_data(current_page=page)
    text = translate(
        language,
        "search_results_page",
        query=html.escape(_shorten(query, 120)),
        page=page,
        total_pages=total_pages,
    )
    await message.edit_text(
        text,
        reply_markup=search_results_keyboard(
            tracks=tracks,
            search_id=search_id,
            page=page,
            page_ranges=page_ranges,
            language=language,
        ),
    )
    return True


def search_results_keyboard(
    tracks: list[Track],
    search_id: str,
    page: int,
    page_ranges: list[tuple[int, int]],
    language: str,
) -> InlineKeyboardMarkup:
    total_pages = len(page_ranges)
    start, end = page_ranges[page - 1]
    page_tracks = tracks[start:end]
    rows = [
        [
            InlineKeyboardButton(
                text=translate(
                    language,
                    "song_button",
                    artist=track.artist,
                    title=track.title,
                )[:64],
                callback_data=f"song:{search_id}:{start + offset}",
            )
        ]
        for offset, track in enumerate(page_tracks)
    ]

    navigation: list[InlineKeyboardButton] = []
    if page > 1:
        navigation.append(
            InlineKeyboardButton(
                text=translate(language, "previous_page"),
                callback_data=f"page:{search_id}:{page - 1}",
            )
        )
    if page < total_pages:
        navigation.append(
            InlineKeyboardButton(
                text=translate(language, "next_page"),
                callback_data=f"page:{search_id}:{page + 1}",
            )
        )
    if navigation:
        rows.append(navigation)
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("page:"))
async def handle_page_navigation(
    callback: CallbackQuery,
    state: FSMContext,
    repository: UserRepository,
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    parsed = _parse_callback(callback.data or "", "page", 3)
    language = await repository.get_language(callback.from_user.id) or "en"
    if parsed is None:
        await callback.answer(translate(language, "selection_expired"), show_alert=True)
        return

    search_id, page = parsed
    updated = await render_result_page(
        callback.message,
        state,
        language,
        search_id,
        requested_page=page,
    )
    if not updated:
        await callback.answer(translate(language, "selection_expired"), show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("song:"))
async def handle_song_selection(
    callback: CallbackQuery,
    state: FSMContext,
    repository: UserRepository,
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    parsed = _parse_callback(callback.data or "", "song", 3)
    language = await repository.get_language(callback.from_user.id) or "en"
    if parsed is None:
        await callback.answer(translate(language, "selection_expired"), show_alert=True)
        return

    search_id, index = parsed
    search = await get_current_search(state, search_id)
    if search is None or index < 0 or index >= len(search["tracks"]):
        await callback.answer(translate(language, "selection_expired"), show_alert=True)
        return
    track: Track = search["tracks"][index]

    await callback.message.edit_text(
        translate(
            language,
            "song_actions",
            artist=html.escape(track.artist),
            title=html.escape(track.title),
        ),
        reply_markup=song_action_keyboard(search_id, index, language),
    )
    await callback.answer()


def song_action_keyboard(
    search_id: str,
    index: int,
    language: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "listen_button"),
                    callback_data=f"send:{search_id}:{index}:listen",
                ),
                InlineKeyboardButton(
                    text=translate(language, "download_button"),
                    callback_data=f"send:{search_id}:{index}:download",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_results"),
                    callback_data=f"back:{search_id}",
                )
            ],
        ]
    )


@router.callback_query(F.data.startswith("back:"))
async def handle_back_to_results(
    callback: CallbackQuery,
    state: FSMContext,
    repository: UserRepository,
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    parts = (callback.data or "").split(":")
    language = await repository.get_language(callback.from_user.id) or "en"
    if len(parts) != 2:
        await callback.answer(translate(language, "selection_expired"), show_alert=True)
        return

    state_data = await state.get_data()
    search_id = parts[1]
    if state_data.get("current_search_id") != search_id:
        await callback.answer(translate(language, "selection_expired"), show_alert=True)
        return
    page = int(state_data.get("current_page", 1))
    updated = await render_result_page(
        callback.message,
        state,
        language,
        search_id,
        requested_page=page,
    )
    if not updated:
        await callback.answer(translate(language, "selection_expired"), show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("send:"))
async def handle_send_audio(
    callback: CallbackQuery,
    state: FSMContext,
    repository: UserRepository,
    preview_downloader: PreviewDownloader,
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    parsed = _parse_audio_callback(callback.data or "")
    language = await repository.get_language(callback.from_user.id) or "en"
    if parsed is None:
        await callback.answer(translate(language, "selection_expired"), show_alert=True)
        return

    search_id, index = parsed
    search = await get_current_search(state, search_id)
    if search is None or index < 0 or index >= len(search["tracks"]):
        await callback.answer(translate(language, "selection_expired"), show_alert=True)
        return
    track: Track = search["tracks"][index]
    await callback.answer()

    status = await callback.message.answer(
        translate(language, "downloading_preview")
    )
    if not track.preview_url:
        await status.edit_text(translate(language, "preview_unavailable"))
        return

    try:
        audio_data = await preview_downloader.download(track.preview_url)
    except PreviewDownloadError:
        logger.exception("Audio preview download failed")
        await status.edit_text(translate(language, "download_failed"))
        return

    caption = translate(
        language,
        "audio_caption",
        title=html.escape(track.title),
        artist=html.escape(track.artist),
    )
    filename = preview_downloader.filename_for(track.preview_url)
    try:
        await callback.message.answer_audio(
            audio=BufferedInputFile(audio_data, filename=filename),
            title=track.title,
            performer=track.artist,
            caption=caption,
        )
    except TelegramAPIError:
        logger.exception("Telegram audio upload failed")
        await status.edit_text(translate(language, "download_failed"))
        return

    try:
        await status.delete()
    except TelegramAPIError:
        logger.debug("Could not remove audio download status message")


async def get_current_search(
    state: FSMContext,
    search_id: str,
) -> dict[str, str | int | list[Track]] | None:
    data = await state.get_data()
    if data.get("current_search_id") != search_id:
        return None
    try:
        if time.time() - float(data["search_created_at"]) >= SEARCH_STATE_TTL_SECONDS:
            return None
        query = str(data["search_query"])
        page = int(data["current_page"])
        stored_tracks = data["current_search_results"]
        tracks = [Track(**track_data) for track_data in stored_tracks]
        return {"query": query, "page": page, "tracks": tracks}
    except (KeyError, TypeError, ValueError):
        return None


def _parse_callback(
    data: str,
    action: str,
    expected_parts: int,
) -> tuple[str, int] | None:
    parts = data.split(":")
    if len(parts) != expected_parts or parts[0] != action:
        return None
    try:
        index = int(parts[2])
    except ValueError:
        return None
    return (parts[1], index) if index >= 0 else None


def _parse_audio_callback(data: str) -> tuple[str, int] | None:
    parts = data.split(":")
    if (
        len(parts) != 4
        or parts[0] != "send"
        or parts[3] not in {"listen", "download"}
    ):
        return None
    try:
        index = int(parts[2])
    except ValueError:
        return None
    return (parts[1], index) if index >= 0 else None


async def _language_for_message(
    message: Message,
    repository: UserRepository,
) -> str:
    user_id = message.from_user.id if message.from_user else 0
    return await repository.get_language(user_id) or "en"


def _shorten(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _page_ranges(result_count: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    offset = 0
    page = 1
    while offset < result_count:
        has_previous = page > 1
        max_without_next = MAX_BUTTONS_PER_PAGE - int(has_previous)
        remaining = result_count - offset
        if remaining <= max_without_next:
            page_size = remaining
        else:
            page_size = MAX_BUTTONS_PER_PAGE - int(has_previous) - 1
        ranges.append((offset, offset + page_size))
        offset += page_size
        page += 1
    return ranges

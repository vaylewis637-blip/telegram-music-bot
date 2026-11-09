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
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from music_bot.config import Settings
from music_bot.handlers.access import require_access
from music_bot.handlers.menu_editor import home_button
from music_bot.i18n import translate
from music_bot.models import Track
from music_bot.services.music_search import MusicSearch, MusicSearchError
from music_bot.services.preview_downloader import PreviewDownloadError, PreviewDownloader
from music_bot.services.user_repository import UserRepository
from music_bot.states import SearchState

router = Router(name="search")
logger = logging.getLogger(__name__)
MAX_BUTTONS_PER_PAGE = 5
SEARCH_STATE_TTL_SECONDS = 3600


@router.message(Command("search"))
async def handle_search_command(message: Message, state: FSMContext, bot: Bot, settings: Settings, repository: UserRepository, music_search: MusicSearch) -> None:
    if not await require_access(message, state, bot, settings, repository):
        return
    query = (message.text or "").partition(" ")[2].strip()
    if not query:
        await state.set_state(SearchState.waiting_for_query)
        await message.answer("🔍 Отправь название песни или исполнителя для поиска.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[home_button()]))
        return
    await search_and_reply(message, query, settings, music_search, state, "ru")


@router.message(SearchState.waiting_for_query, F.text)
async def handle_text_search(message: Message, state: FSMContext, bot: Bot, settings: Settings, repository: UserRepository, music_search: MusicSearch) -> None:
    query = (message.text or "").strip()
    if not query or query.startswith("/"):
        return
    if not await require_access(message, state, bot, settings, repository):
        return
    await search_and_reply(message, query, settings, music_search, state, "ru")


async def search_and_reply(message: Message, query: str, settings: Settings, music_search: MusicSearch, state: FSMContext, language: str = "ru") -> None:
    await state.update_data(current_search_id=None, search_query=query, current_page=1, current_search_results=[], search_created_at=time.time())
    status = await message.answer("🔍 Ищу в музыкальном каталоге…")
    try:
        tracks = await music_search.search(query=query, limit=settings.search_results_limit)
    except MusicSearchError:
        logger.exception("Music catalog search failed")
        await status.edit_text("🔍 Музыкальный каталог временно недоступен. Попробуй позже.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[home_button()]))
        return
    if not tracks:
        await status.edit_text(f"🔍 По запросу «{html.escape(_shorten(query, 120))}» ничего не найдено.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[home_button()]))
        return
    search_id = secrets.token_hex(4)
    await state.update_data(current_search_id=search_id, search_query=query, current_page=1, current_search_results=[asdict(track) for track in tracks], search_created_at=time.time())
    await render_result_page(status, state, language, search_id, 1)


async def render_result_page(message: Message, state: FSMContext, language: str, search_id: str, requested_page: int | None = None) -> bool:
    search = await get_current_search(state, search_id)
    if search is None:
        return False
    tracks: list[Track] = search["tracks"]
    page_ranges = _page_ranges(len(tracks))
    page = requested_page if requested_page is not None else int(search["page"])
    if not 1 <= page <= len(page_ranges):
        return False
    await state.update_data(current_page=page)
    query = html.escape(_shorten(str(search["query"]), 120))
    await message.edit_text(f"🔍 Результаты по запросу «{query}» — страница {page}/{len(page_ranges)}. Выбери песню:", reply_markup=search_results_keyboard(tracks, search_id, page, page_ranges, language))
    return True


def search_results_keyboard(tracks: list[Track], search_id: str, page: int, page_ranges: list[tuple[int, int]], language: str) -> InlineKeyboardMarkup:
    start, end = page_ranges[page - 1]
    rows = [[InlineKeyboardButton(text=f"{track.artist} — {track.title}"[:64], callback_data=f"song:{search_id}:{start + offset}")] for offset, track in enumerate(tracks[start:end])]
    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️ Предыдущая", callback_data=f"page:{search_id}:{page - 1}"))
    if page < len(page_ranges):
        nav.append(InlineKeyboardButton(text="➡️ Следующая", callback_data=f"page:{search_id}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append(home_button())
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("page:"))
async def handle_page_navigation(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    parts = (callback.data or "").split(":")
    try:
        search_id, page = parts[1], int(parts[2])
    except (IndexError, ValueError):
        await callback.answer("Выбор устарел. Выполни поиск ещё раз.", show_alert=True)
        return
    if not await render_result_page(callback.message, state, "ru", search_id, page):
        await callback.answer("Результаты устарели. Выполни поиск ещё раз.", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("song:"))
async def handle_song_selection(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    parsed = _parse_callback(callback.data or "", "song")
    if parsed is None:
        await callback.answer("Результаты устарели.", show_alert=True)
        return
    search_id, index = parsed
    search = await get_current_search(state, search_id)
    if search is None or index >= len(search["tracks"]):
        await callback.answer("Результаты устарели.", show_alert=True)
        return
    track: Track = search["tracks"][index]
    await callback.message.edit_text(f"🎵 <b>{html.escape(track.title)}</b> — {html.escape(track.artist)}\n\nВыбери действие. Каталог предоставляет аудиофрагменты для прослушивания.", reply_markup=song_action_keyboard(search_id, index))
    await callback.answer()


def song_action_keyboard(search_id: str, index: int, language: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬇️ Скачать песню", callback_data=f"send:{search_id}:{index}:download")],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit:{search_id}:{index}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back:{search_id}"), *home_button()],
    ])


@router.callback_query(F.data.startswith("back:"))
async def handle_back_to_results(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    search_id = (callback.data or "").partition(":")[2]
    data = await state.get_data()
    if data.get("current_search_id") != search_id or not await render_result_page(callback.message, state, "ru", search_id, int(data.get("current_page", 1))):
        await callback.answer("Результаты устарели. Выполни поиск ещё раз.", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("send:"))
async def handle_send_audio(callback: CallbackQuery, state: FSMContext, repository: UserRepository, preview_downloader: PreviewDownloader, bot: Bot) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    parts = (callback.data or "").split(":")
    try:
        search_id, index = parts[1], int(parts[2])
    except (IndexError, ValueError):
        await callback.answer("Результаты устарели.", show_alert=True)
        return
    search = await get_current_search(state, search_id)
    if search is None or index >= len(search["tracks"]):
        await callback.answer("Результаты устарели.", show_alert=True)
        return
    track: Track = search["tracks"][index]
    await callback.answer()
    status = await callback.message.answer("⬇️ Загружаю аудиофрагмент из каталога…")
    if not track.preview_url:
        await status.edit_text("Для этой песни нет доступного фрагмента.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[home_button()]))
        return
    try:
        audio_data = await preview_downloader.download(track.preview_url)
        filename = preview_downloader.filename_for(track.preview_url)
        cover = await _bot_avatar(bot)
        if cover:
            from music_bot.services.audio_editor import apply_metadata, to_mp3
            audio_data = apply_metadata(to_mp3(audio_data, filename.rsplit(".", 1)[-1]), track.title, track.artist, track.album, cover)
            filename = filename.rsplit(".", 1)[0] + ".mp3"
        await callback.message.answer_audio(audio=BufferedInputFile(audio_data, filename=filename), title=track.title, performer=track.artist, caption=f"🎵 <b>{html.escape(track.title)}</b> — {html.escape(track.artist)}\nАудиофрагмент из каталога.")
        await status.delete()
    except (PreviewDownloadError, TelegramAPIError, Exception) as error:
        logger.exception("Preview delivery failed")
        await status.edit_text("Не удалось загрузить или отправить фрагмент. Попробуй ещё раз.")


async def _bot_avatar(bot: Bot) -> bytes | None:
    try:
        photos = await bot.get_user_profile_photos(user_id=bot.id, limit=1)
        if not photos.photos:
            return None
        file = await bot.get_file(photos.photos[0][-1].file_id)
        import io
        target = io.BytesIO()
        await bot.download_file(file.file_path, destination=target)
        from music_bot.services.audio_editor import normalize_cover
        return normalize_cover(target.getvalue())
    except Exception:
        logger.info("Bot avatar unavailable for audio cover", exc_info=True)
        return None


async def get_current_search(state: FSMContext, search_id: str) -> dict[str, str | int | list[Track]] | None:
    data = await state.get_data()
    if data.get("current_search_id") != search_id:
        return None
    try:
        if time.time() - float(data["search_created_at"]) >= SEARCH_STATE_TTL_SECONDS:
            return None
        return {"query": str(data["search_query"]), "page": int(data["current_page"]), "tracks": [Track(**item) for item in data["current_search_results"]]}
    except (KeyError, TypeError, ValueError):
        return None


def _parse_callback(value: str, action: str) -> tuple[str, int] | None:
    parts = value.split(":")
    if len(parts) != 3 or parts[0] != action:
        return None
    try:
        index = int(parts[2])
    except ValueError:
        return None
    return (parts[1], index) if index >= 0 else None


def _shorten(value: str, limit: int) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[:limit - 1].rstrip() + "…"


def _page_ranges(count: int) -> list[tuple[int, int]]:
    return [(start, min(start + MAX_BUTTONS_PER_PAGE, count)) for start in range(0, count, MAX_BUTTONS_PER_PAGE)]

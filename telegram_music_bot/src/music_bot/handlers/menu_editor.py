from __future__ import annotations

import base64
import html
import io
import logging
import os
import secrets
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from music_bot.config import Settings
from music_bot.handlers.access import require_access
from music_bot.models import Track
from music_bot.services.audio_editor import MAX_AUDIO_BYTES, AudioEditError, apply_metadata, edit_speed, normalize_cover, parse_time_range, save_audio, to_mp3, trim_audio
from music_bot.services.music_search import MusicSearch
from music_bot.services.preview_downloader import PreviewDownloadError, PreviewDownloader
from music_bot.services.user_repository import UserRepository
from music_bot.states import EditorState, SearchState

router = Router(name="menu_and_editor")
logger = logging.getLogger(__name__)
HOME_TEXT = "🎵 Главное меню\n\nВыберите действие. Я подскажу, что делать дальше."


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Поиск песни", callback_data="menu:search")],
        [InlineKeyboardButton(text="✏️ Редактировать песню", callback_data="menu:edit")],
    ])


def home_button() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")]


def editor_keyboard(changed: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🏷 Сменить теги", callback_data="editor:tags")],
        [InlineKeyboardButton(text="🐢 Замедлить песню", callback_data="editor:speed")],
        [InlineKeyboardButton(text="🖼 Изменить фото песни", callback_data="editor:cover")],
        [InlineKeyboardButton(text="✂️ Обрезать песню", callback_data="editor:trim")],
    ]
    if changed:
        rows.append([InlineKeyboardButton(text="💾 Сохранить", callback_data="editor:save"), InlineKeyboardButton(text="👀 Просмотреть", callback_data="editor:preview")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад к результатам", callback_data="editor:results"), *home_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tab_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="editor:back"), *home_button()]])


def _speed_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="0.75x", callback_data="speed:0.75"), InlineKeyboardButton(text="0.9x", callback_data="speed:0.9"), InlineKeyboardButton(text="1.25x", callback_data="speed:1.25")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="editor:back"), *home_button()],
    ])


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, bot: Bot, settings: Settings, repository: UserRepository) -> None:
    await state.clear()
    if await require_access(message, state, bot, settings, repository):
        await message.answer(HOME_TEXT, reply_markup=home_keyboard())


@router.callback_query(F.data == "home")
async def show_home(callback: CallbackQuery, state: FSMContext, bot: Bot, settings: Settings, repository: UserRepository) -> None:
    await state.clear()
    await callback.answer()
    if isinstance(callback.message, Message) and await require_access(callback.message, state, bot, settings, repository):
        await callback.message.answer(HOME_TEXT, reply_markup=home_keyboard())


@router.callback_query(F.data.in_({"menu:search", "menu:edit"}))
async def start_menu_action(callback: CallbackQuery, state: FSMContext, bot: Bot, settings: Settings, repository: UserRepository) -> None:
    if not isinstance(callback.message, Message) or not await require_access(callback.message, state, bot, settings, repository):
        await callback.answer()
        return
    await state.set_state(SearchState.waiting_for_query)
    await callback.answer()
    label = "поиска" if callback.data == "menu:search" else "выбора песни для редактирования"
    await callback.message.answer(f"🔍 Отправь название песни или исполнителя для {label}. Например: Daft Punk.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[home_button()]))


@router.message(SearchState.waiting_for_query, F.text)
async def query_from_menu(message: Message, state: FSMContext, bot: Bot, settings: Settings, repository: UserRepository, music_search: MusicSearch) -> None:
    query = (message.text or "").strip()
    if not query or query.startswith("/"):
        return
    if not await require_access(message, state, bot, settings, repository):
        return
    from music_bot.handlers.search import search_and_reply
    await search_and_reply(message, query, settings, music_search, state, "ru")


@router.callback_query(F.data.startswith("edit:"))
async def begin_edit(callback: CallbackQuery, state: FSMContext, bot: Bot, settings: Settings, repository: UserRepository, preview_downloader: PreviewDownloader) -> None:
    if not isinstance(callback.message, Message) or not await require_access(callback.message, state, bot, settings, repository):
        await callback.answer()
        return
    parts = (callback.data or "").split(":")
    try:
        search_id, index = parts[1], int(parts[2])
    except (IndexError, ValueError):
        await callback.answer("Выбор устарел. Выполни поиск ещё раз.", show_alert=True)
        return
    from music_bot.handlers.search import get_current_search
    result = await get_current_search(state, search_id)
    if result is None or index >= len(result["tracks"]):
        await callback.answer("Результаты устарели. Выполни поиск ещё раз.", show_alert=True)
        return
    track: Track = result["tracks"][index]
    if not track.preview_url:
        await callback.answer("Для редактирования нет аудиофрагмента.", show_alert=True)
        return
    await callback.answer()
    status = await callback.message.answer("✏️ Загружаю доступный аудиофрагмент для редактора…")
    try:
        raw = await preview_downloader.download(track.preview_url)
        audio = to_mp3(raw, preview_downloader.filename_for(track.preview_url).rsplit(".", 1)[-1])
        cover = await bot_avatar(bot)
        audio = apply_metadata(audio, track.title, track.artist, track.album, cover)
    except (PreviewDownloadError, AudioEditError) as error:
        await status.edit_text(f"Не удалось открыть аудио: {html.escape(str(error))}")
        return
    data = await state.get_data()
    encoded = base64.b64encode(audio).decode("ascii")
    await state.set_state(EditorState.editing)
    await state.set_data({**data, "editor_original": encoded, "editor_working": encoded, "editor_title": track.title, "editor_artist": track.artist, "editor_album": track.album, "editor_cover": base64.b64encode(cover).decode("ascii") if cover else "", "editor_search_id": search_id, "editor_track_index": index, "editor_changed": False})
    await status.edit_text(_editor_text(track), reply_markup=editor_keyboard(False))


@router.callback_query(F.data == "editor:results")
async def back_to_results(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    data = await state.get_data()
    search_id = str(data.get("editor_search_id", ""))
    from music_bot.handlers.search import render_result_page
    await state.set_state(SearchState.waiting_for_query)
    if not await render_result_page(callback.message, state, "ru", search_id, int(data.get("current_page", 1))):
        await callback.message.answer("Результаты устарели. Выполни поиск ещё раз.", reply_markup=home_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("editor:"))
async def editor_action(callback: CallbackQuery, state: FSMContext) -> None:
    action = (callback.data or "").split(":", 1)[1]
    data = await state.get_data()
    if not data.get("editor_working"):
        await callback.answer("Сначала выбери песню для редактирования.", show_alert=True)
        return
    if action == "back":
        await state.set_state(EditorState.editing)
        if isinstance(callback.message, Message):
            await callback.message.edit_text(_editor_text_from_data(data), reply_markup=editor_keyboard(bool(data.get("editor_changed"))))
        await callback.answer()
        return
    prompts = {
        "tags": ("🏷 Отправь теги в формате:\n<code>!tags Песня | Имя артиста | Название альбома</code>\nTitle и artist — отдельные поля.", EditorState.waiting_for_tags),
        "speed": ("🐢 Выбери скорость воспроизведения:", EditorState.waiting_for_speed),
        "cover": ("🖼 Отправь изображение обложки песней в формате JPG или PNG.", EditorState.waiting_for_cover),
        "trim": ("✂️ Укажи начало и конец в формате мм:сс — мм:сс. Пример: <code>0:30 — 1:15</code>.", EditorState.waiting_for_trim),
    }
    if action in prompts:
        text, next_state = prompts[action]
        await state.set_state(next_state)
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.answer(text, reply_markup=_speed_keyboard() if action == "speed" else tab_keyboard())
        return
    if action in {"save", "preview"}:
        await callback.answer()
        await send_audio(callback.message, data, save=action == "save")
        return
    await callback.answer("Неизвестное действие.", show_alert=True)


@router.callback_query(F.data.startswith("speed:"))
async def speed_choice(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        speed = float((callback.data or "").split(":", 1)[1])
        audio = edit_speed(_decode(data, "editor_working"), speed)
        data = await update_audio(state, data, audio)
        await state.set_state(EditorState.editing)
        await callback.answer(f"Скорость изменена: {speed}x")
        if isinstance(callback.message, Message):
            await callback.message.answer(_editor_text_from_data(data), reply_markup=editor_keyboard(True))
    except (ValueError, KeyError, AudioEditError) as error:
        await callback.answer(str(error), show_alert=True)


@router.message(EditorState.waiting_for_tags, F.text)
async def change_tags(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    parts = [part.strip() for part in value[6:].split("|")] if value.startswith("!tags ") else []
    if len(parts) != 3 or not all(parts):
        await message.answer("Формат: <code>!tags Песня | Имя артиста | Название альбома</code>", reply_markup=tab_keyboard())
        return
    data = await state.get_data()
    try:
        audio = apply_metadata(_decode(data, "editor_working"), *parts, _decode_optional(data, "editor_cover"))
        data.update(editor_title=parts[0], editor_artist=parts[1], editor_album=parts[2])
        data = await update_audio(state, data, audio)
        await state.set_state(EditorState.editing)
        await message.answer("✅ Теги изменены: title и artist сохранены отдельно.\n" + _editor_text_from_data(data), reply_markup=editor_keyboard(True))
    except (KeyError, AudioEditError) as error:
        await message.answer(f"Не удалось изменить теги: {html.escape(str(error))}", reply_markup=tab_keyboard())


@router.message(EditorState.waiting_for_trim, F.text)
async def change_trim(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        start, end = parse_time_range(message.text or "")
        audio = trim_audio(_decode(data, "editor_working"), start, end)
        audio = apply_metadata(audio, str(data["editor_title"]), str(data["editor_artist"]), str(data["editor_album"]), _decode_optional(data, "editor_cover"))
        data = await update_audio(state, data, audio)
        await state.set_state(EditorState.editing)
        await message.answer("✅ Фрагмент обрезан.\n" + _editor_text_from_data(data), reply_markup=editor_keyboard(True))
    except (KeyError, AudioEditError) as error:
        await message.answer(f"Не удалось обрезать аудио: {html.escape(str(error))}", reply_markup=tab_keyboard())


@router.message(EditorState.waiting_for_cover, F.photo)
async def change_cover(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    try:
        file = await bot.get_file(message.photo[-1].file_id)
        output = io.BytesIO()
        await bot.download_file(file.file_path, destination=output)
        cover = normalize_cover(output.getvalue())
        audio = apply_metadata(_decode(data, "editor_working"), str(data["editor_title"]), str(data["editor_artist"]), str(data["editor_album"]), cover)
        data["editor_cover"] = base64.b64encode(cover).decode("ascii")
        data = await update_audio(state, data, audio)
        await state.set_state(EditorState.editing)
        await message.answer("✅ Обложка добавлена.\n" + _editor_text_from_data(data), reply_markup=editor_keyboard(True))
    except (TelegramAPIError, KeyError, AudioEditError) as error:
        await message.answer(f"Не удалось добавить обложку: {html.escape(str(error))}", reply_markup=tab_keyboard())


@router.message(EditorState.waiting_for_cover)
async def wrong_cover(message: Message) -> None:
    await message.answer("Отправь изображение как фото, пожалуйста.", reply_markup=tab_keyboard())


@router.message(EditorState.waiting_for_tags)
async def wrong_tags(message: Message) -> None:
    await message.answer("Отправь текст тегов: <code>!tags Песня | Имя артиста | Название альбома</code>", reply_markup=tab_keyboard())


@router.message(EditorState.waiting_for_trim)
async def wrong_trim(message: Message) -> None:
    await message.answer("Отправь время текстом, например: <code>0:30 — 1:15</code>.", reply_markup=tab_keyboard())


async def update_audio(state: FSMContext, data: dict, audio: bytes) -> dict:
    data["editor_working"] = base64.b64encode(audio).decode("ascii")
    data["editor_changed"] = True
    await state.update_data(editor_working=data["editor_working"], editor_changed=True)
    return data


async def bot_avatar(bot: Bot) -> bytes | None:
    try:
        photos = await bot.get_user_profile_photos(user_id=bot.id, limit=1)
        if not photos.photos:
            return None
        file = await bot.get_file(photos.photos[0][-1].file_id)
        output = io.BytesIO()
        await bot.download_file(file.file_path, destination=output)
        return normalize_cover(output.getvalue())
    except (TelegramAPIError, AudioEditError):
        logger.info("Не удалось получить аватар бота для обложки", exc_info=True)
        return None


async def send_audio(message: Message | None, data: dict, save: bool) -> None:
    if not isinstance(message, Message):
        return
    try:
        audio = _decode(data, "editor_working")
        title = str(data.get("editor_title", "Песня"))
        filename = _safe_filename(title) + ".mp3"
        if save:
            user_id = message.from_user.id if message.from_user else 0
            filename = f"{_safe_filename(title)}-{secrets.token_hex(3)}.mp3"
            save_audio(audio, Path(os.getenv("EDITED_TRACKS_DIR", "data/edited_tracks")) / str(user_id) / filename)
        await message.answer_audio(audio=BufferedInputFile(audio, filename=filename), title=title, performer=str(data.get("editor_artist", "")), caption="💾 Файл сохранён." if save else "👀 Предварительное прослушивание. Изменения пока не сохранены.")
    except (KeyError, AudioEditError, TelegramAPIError) as error:
        await message.answer(f"Не удалось отправить аудио: {html.escape(str(error))}")


def _editor_text(track: Track) -> str:
    return f"✏️ Редактор: <b>{html.escape(track.artist)} — {html.escape(track.title)}</b>\nРедактируется доступный а��диофрагмент из каталога."


def _editor_text_from_data(data: dict) -> str:
    status = "Изменения ожидают сохранения." if data.get("editor_changed") else "Изменения ещё не внесены."
    return f"✏️ Редактор: <b>{html.escape(str(data.get('editor_artist', '')))} — {html.escape(str(data.get('editor_title', '')))}</b>\n{status}"


def _decode(data: dict, key: str) -> bytes:
    value = data.get(key)
    if not isinstance(value, str):
        raise KeyError(key)
    audio = base64.b64decode(value, validate=True)
    if len(audio) > MAX_AUDIO_BYTES:
        raise AudioEditError("Размер аудио превышает 15 МБ.")
    return audio


def _decode_optional(data: dict, key: str) -> bytes | None:
    value = data.get(key)
    return base64.b64decode(value, validate=True) if isinstance(value, str) and value else None


def _safe_filename(value: str) -> str:
    safe = "".join(char for char in value if char.isalnum() or char in " -_").strip()
    return (safe[:80] or "music").replace(" ", "_")

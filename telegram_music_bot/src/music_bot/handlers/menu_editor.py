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
from music_bot.models import Track
from music_bot.services.audio_editor import (
    MAX_AUDIO_BYTES,
    AudioEditError,
    apply_metadata,
    edit_speed,
    normalize_cover,
    parse_time_range,
    save_audio,
    to_mp3,
    trim_audio,
)
from music_bot.services.preview_downloader import PreviewDownloadError, PreviewDownloader
from music_bot.services.user_repository import UserRepository
from music_bot.states import EditorState, SearchState

router = Router(name="menu_and_editor")
logger = logging.getLogger(__name__)

HOME_TEXT = "🎵 Главное меню\n\nВыберите действие. Я подскажу, что делать дальше."
HOME_CALLBACK = "home"
EDITOR_BACK = "editor:back"


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Поиск песни", callback_data="menu:search")],
        [InlineKeyboardButton(text="✏️ Редактировать песню", callback_data="menu:edit")],
    ])


def home_button() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="🏠 Главное меню", callback_data=HOME_CALLBACK)]


def editor_keyboard(has_changes: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🏷 Сменить теги", callback_data="editor:tags")],
        [InlineKeyboardButton(text="🐢 Замедлить песню", callback_data="editor:speed")],
        [InlineKeyboardButton(text="🖼 Изменить фото песни", callback_data="editor:cover")],
        [InlineKeyboardButton(text="✂️ Обрезать песню", callback_data="editor:trim")],
    ]
    if has_changes:
        rows.extend([
            [InlineKeyboardButton(text="💾 Сохранить", callback_data="editor:save"),
             InlineKeyboardButton(text="👀 Просмотреть", callback_data="editor:preview")],
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="editor:results"), *home_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tab_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data=EDITOR_BACK), *home_button()]])


def speed_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="0.75x", callback_data="speed:0.75"),
         InlineKeyboardButton(text="0.9x", callback_data="speed:0.9"),
         InlineKeyboardButton(text="1.25x", callback_data="speed:1.25")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=EDITOR_BACK), *home_button()],
    ])


@router.callback_query(F.data == HOME_CALLBACK)
async def show_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(HOME_TEXT, reply_markup=home_keyboard())


@router.callback_query(F.data.in_({"menu:search", "menu:edit"}))
async def start_menu_action(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchState.waiting_for_query)
    action = "поиска" if callback.data == "menu:search" else "выбора песни для редактирования"
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            f"🔍 Отправь название песни или исполнителя для {action}. Например: Daft Punk.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[home_button()]),
        )


@router.message(F.text == "🏠 Главное меню")
async def show_home_text(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(HOME_TEXT, reply_markup=home_keyboard())


@router.callback_query(F.data.startswith("edit:"))
async def begin_edit_from_search(
    callback: CallbackQuery,
    state: FSMContext,
    repository: UserRepository,
    preview_downloader: PreviewDownloader,
    bot: Bot,
) -> None:
    if not isinstance(callback.message, Message) or callback.from_user is None:
        await callback.answer()
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Выбор песни устарел. Выполни поиск ещё раз.", show_alert=True)
        return
    try:
        index = int(parts[2])
    except ValueError:
        await callback.answer("Выбор песни устарел. Выполни поиск ещё раз.", show_alert=True)
        return
    from music_bot.handlers.search import get_current_search

    search = await get_current_search(state, parts[1])
    if search is None or index >= len(search["tracks"]):
        await callback.answer("Результаты устарели. Выполни поиск ещё раз.", show_alert=True)
        return
    track: Track = search["tracks"][index]
    if not track.preview_url:
        await callback.answer("Для этой песни нет доступного фрагмента для редактирования.", show_alert=True)
        return
    await callback.answer()
    status = await callback.message.answer("✏️ Загружаю до��тупный аудиофрагмент для редактора…")
    try:
        source = await preview_downloader.download(track.preview_url)
        audio = to_mp3(source, preview_downloader.filename_for(track.preview_url).lstrip("."))
        cover = await bot_avatar(bot)
        audio = apply_metadata(audio, track.title, track.artist, track.album, cover)
    except (PreviewDownloadError, AudioEditError) as error:
        await status.edit_text(f"Не удалось открыть аудио: {html.escape(str(error))}")
        return
    data = await state.get_data()
    await state.set_state(EditorState.editing)
    await state.set_data({
        **data,
        "editor_original": base64.b64encode(audio).decode("ascii"),
        "editor_working": base64.b64encode(audio).decode("ascii"),
        "editor_title": track.title,
        "editor_artist": track.artist,
        "editor_album": track.album,
        "editor_cover": base64.b64encode(cover).decode("ascii") if cover else "",
        "editor_search_id": parts[1],
        "editor_track_index": index,
        "editor_changed": False,
    })
    await status.edit_text(editor_text(track), reply_markup=editor_keyboard(False))


@router.callback_query(F.data == "editor:results")
async def editor_back_to_results(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    search_id = data.get("editor_search_id")
    page = data.get("current_page", 1)
    await callback.answer()
    if isinstance(callback.message, Message) and search_id:
        from music_bot.handlers.search import render_result_page
        await state.set_state(None)
        updated = await render_result_page(callback.message, state, "ru", str(search_id), int(page))
        if not updated:
            await callback.message.answer("Результаты поиска устарели.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[home_button()]))


@router.callback_query(F.data.startswith("editor:"))
async def editor_actions(callback: CallbackQuery, state: FSMContext) -> None:
    action = (callback.data or "").split(":", 1)[1]
    data = await state.get_data()
    if not data.get("editor_working"):
        await callback.answer("Сначала выбери песню для редактирования.", show_alert=True)
        return
    if action == "back":
        await state.set_state(EditorState.editing)
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.edit_text(editor_text_from_data(data), reply_markup=editor_keyboard(bool(data.get("editor_changed"))))
        return
    prompts = {
        "tags": ("🏷 Отправь теги в формате:\n<code>!tags Песня | Имя артиста | Название альбома</code>\nНазвание и исполнитель — отдельные поля.", EditorState.waiting_for_tags),
        "speed": ("🐢 Выбери скорость воспроизведения:", EditorState.waiting_for_speed),
        "cover": ("🖼 Отправь изображение обложки песней. Подойдут JPG или PNG.", EditorState.waiting_for_cover),
        "trim": ("✂️ Укажи начало и конец фрагмента в формате мм:сс — мм:сс.\nНапример: <code>0:30 — 1:15</code>.", EditorState.waiting_for_trim),
    }
    if action in prompts:
        text, next_state = prompts[action]
        await state.set_state(next_state)
        await callback.answer()
        if isinstance(callback.message, Message):
            markup = speed_keyboard() if action == "speed" else tab_keyboard()
            await callback.message.answer(text, reply_markup=markup)
        return
    if action in {"preview", "save"}:
        await callback.answer()
        await send_working_audio(callback.message, data, saved=(action == "save"))
        return
    await callback.answer("Неизвестное действие.", show_alert=True)


@router.callback_query(F.data.startswith("speed:"))
async def apply_speed_choice(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        speed = float((callback.data or "").split(":", 1)[1])
        data = await state.get_data()
        audio = _decode(data, "editor_working")
        changed = edit_speed(audio, speed)
        data = await update_working_audio(state, data, changed)
        await state.set_state(EditorState.editing)
        await callback.answer(f"Скорость изменена: {speed}x")
        if isinstance(callback.message, Message):
            await callback.message.answer(f"✅ Скорость изменена на {speed}x.\n\n{editor_text_from_data(data)}", reply_markup=editor_keyboard(True))
    except (ValueError, KeyError, AudioEditError) as error:
        await callback.answer(str(error), show_alert=True)


@router.message(EditorState.waiting_for_tags, F.text)
async def apply_tags(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not value.startswith("!tags "):
        await message.answer("Формат: <code>!tags Песня | Имя артиста | Название альбома</code>", reply_markup=tab_keyboard())
        return
    parts = [part.strip() for part in value[6:].split("|")]
    if len(parts) != 3 or not all(parts):
        await message.answer("Нужно указать все три поля через |: <code>!tags Песня | Имя артиста | Название альбома</code>", reply_markup=tab_keyboard())
        return
    data = await state.get_data()
    try:
        audio = apply_metadata(_decode(data, "editor_working"), *parts, _decode_optional(data, "editor_cover"))
        data.update(editor_title=parts[0], editor_artist=parts[1], editor_album=parts[2])
        data = await update_working_audio(state, data, audio)
        await state.set_state(EditorState.editing)
        await message.answer("✅ Теги изменены. Title и artist сохранены отдельно.\n\n" + editor_text_from_data(data), reply_markup=editor_keyboard(True))
    except (KeyError, AudioEditError) as error:
        await message.answer(f"Не удалось изменить теги: {html.escape(str(error))}", reply_markup=tab_keyboard())


@router.message(EditorState.waiting_for_trim, F.text)
async def apply_trim(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        start_ms, end_ms = parse_time_range(message.text or "")
        audio = trim_audio(_decode(data, "editor_working"), start_ms, end_ms)
        audio = apply_metadata(audio, str(data["editor_title"]), str(data["editor_artist"]), str(data["editor_album"]), _decode_optional(data, "editor_cover"))
        data = await update_working_audio(state, data, audio)
        await state.set_state(EditorState.editing)
        await message.answer("✅ Фрагмент обрезан.\n\n" + editor_text_from_data(data), reply_markup=editor_keyboard(True))
    except (KeyError, AudioEditError) as error:
        await message.answer(f"Не удалось обрезать: {html.escape(str(error))}", reply_markup=tab_keyboard())


@router.message(EditorState.waiting_for_cover, F.photo)
async def apply_cover(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.photo:
        await message.answer("Пришли изображение как фото, пожалуйста.", reply_markup=tab_keyboard())
        return
    data = await state.get_data()
    try:
        photo_file = await bot.get_file(message.photo[-1].file_id)
        buffer = io.BytesIO()
        await bot.download_file(photo_file.file_path, destination=buffer)
        cover = normalize_cover(buffer.getvalue())
        audio = apply_metadata(_decode(data, "editor_working"), str(data["editor_title"]), str(data["editor_artist"]), str(data["editor_album"]), cover)
        data["editor_cover"] = base64.b64encode(cover).decode("ascii")
        data = await update_working_audio(state, data, audio)
        await state.set_state(EditorState.editing)
        await message.answer("✅ Обложка добавлена.\n\n" + editor_text_from_data(data), reply_markup=editor_keyboard(True))
    except (TelegramAPIError, KeyError, AudioEditError) as error:
        await message.answer(f"Не удалось добавить обложку: {html.escape(str(error))}", reply_markup=tab_keyboard())


@router.message(EditorState.waiting_for_cover)
async def wrong_cover_type(message: Message) -> None:
    await message.answer("Отправь изображение как фото, пожалуйста.", reply_markup=tab_keyboard())


@router.message(EditorState.waiting_for_tags)
async def wrong_tags_type(message: Message) -> None:
    await message.answer("Отправь текст тегов: <code>!tags Песня | Имя артиста | Название альбома</code>", reply_markup=tab_keyboard())


@router.message(EditorState.waiting_for_trim)
async def wrong_trim_type(message: Message) -> None:
    await message.answer("Отправь время текстом, например: <code>0:30 — 1:15</code>.", reply_markup=tab_keyboard())


async def update_working_audio(state: FSMContext, data: dict, audio: bytes) -> dict:
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
        target = io.BytesIO()
        await bot.download_file(file.file_path, destination=target)
        return normalize_cover(target.getvalue())
    except (TelegramAPIError, AudioEditError):
        logger.warning("Не удалось получить аватар бота для обложки", exc_info=True)
        return None


async def send_working_audio(message: Message | None, data: dict, saved: bool = False) -> None:
    if not isinstance(message, Message):
        return
    try:
        audio = _decode(data, "editor_working")
        title = str(data.get("editor_title", "Песня"))
        artist = str(data.get("editor_artist", ""))
        filename = f"{_safe_filename(title)}.mp3"
        if saved:
            output_dir = Path(os.getenv("EDITED_TRACKS_DIR", "data/edited_tracks")) / str(message.from_user.id if message.from_user else 0)
            filename = f"{_safe_filename(title)}-{secrets.token_hex(3)}.mp3"
            save_audio(audio, output_dir / filename)
        await message.answer_audio(
            audio=BufferedInputFile(audio, filename=filename),
            title=title,
            performer=artist,
            caption="💾 Готовый файл сохранён." if saved else "👀 Предварительное прослушивание. Изменения пока не сохранены.",
        )
    except (KeyError, AudioEditError, TelegramAPIError) as error:
        await message.answer(f"Не удалось отправить аудио: {html.escape(str(error))}")


def editor_text(track: Track) -> str:
    return f"✏️ Редактор: <b>{html.escape(track.artist)} — {html.escape(track.title)}</b>\nРедактируется доступный аудиофрагмент из каталога. Изменения пока не сохранены."


def editor_text_from_data(data: dict) -> str:
    return f"✏️ Редактор: <b>{html.escape(str(data.get('editor_artist', '')))} — {html.escape(str(data.get('editor_title', '')))}</b>\nВыбери действие. Изменения {'ожидают сохранения' if data.get('editor_changed') else 'ещё не внесены'}."


def _decode(data: dict, key: str) -> bytes:
    value = data.get(key)
    if not isinstance(value, str):
        raise KeyError(key)
    result = base64.b64decode(value, validate=True)
    if len(result) > MAX_AUDIO_BYTES:
        raise AudioEditError("Размер аудио превышает 15 МБ.")
    return result


def _decode_optional(data: dict, key: str) -> bytes | None:
    value = data.get(key)
    return base64.b64decode(value, validate=True) if isinstance(value, str) and value else None


def _safe_filename(value: str) -> str:
    cleaned = "".join(char for char in value if char.isalnum() or char in " -_").strip()
    return (cleaned[:80] or "music").replace(" ", "_")

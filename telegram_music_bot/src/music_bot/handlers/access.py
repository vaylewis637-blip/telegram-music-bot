from __future__ import annotations

import logging
import secrets
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from music_bot.config import RequiredChannel, Settings
from music_bot.i18n import LANGUAGES, translate
from music_bot.services.subscriptions import (
    SubscriptionCheckError,
    find_missing_channels,
)
from music_bot.services.user_repository import UserRepository
from music_bot.states import CaptchaState

router = Router(name="access")
logger = logging.getLogger(__name__)

CAPTCHA_ATTEMPTS = 3
SUBSCRIPTION_CHECK_CALLBACK = "check_required_subscriptions"
LANGUAGE_CALLBACK_PREFIX = "language:"
CAPTCHA_CALLBACK_PREFIX = "captcha:"


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"{LANGUAGE_CALLBACK_PREFIX}{code}",
                )
            ]
            for code, label in LANGUAGES.items()
        ]
    )


def captcha_keyboard(answer: int, challenge_id: str) -> InlineKeyboardMarkup:
    options = {answer}
    while len(options) < 4:
        options.add(secrets.randbelow(19) + 2)
    shuffled_options = list(options)
    secrets.SystemRandom().shuffle(shuffled_options)
    buttons = [
        InlineKeyboardButton(
            text=str(option),
            callback_data=f"{CAPTCHA_CALLBACK_PREFIX}{challenge_id}:{option}",
        )
        for option in shuffled_options
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[buttons[:2], buttons[2:]],
    )


async def issue_captcha(
    message: Message,
    state: FSMContext,
    settings: Settings,
    language: str = "en",
) -> None:
    left = secrets.randbelow(9) + 2
    right = secrets.randbelow(9) + 2
    answer = left + right
    challenge_id = secrets.token_hex(4)
    await state.set_state(CaptchaState.waiting_for_answer)
    await state.set_data(
        {
            "captcha_answer": answer,
            "captcha_challenge_id": challenge_id,
            "captcha_created_at": time.time(),
            "captcha_attempts": 0,
            "captcha_user_id": message.from_user.id if message.from_user else 0,
        }
    )
    await message.answer(
        translate(
            language,
            "captcha_prompt",
            left=left,
            right=right,
            seconds=settings.captcha_ttl_seconds,
        ),
        reply_markup=captcha_keyboard(answer, challenge_id),
    )


def subscription_keyboard(
    settings: Settings,
    channels: tuple[RequiredChannel, ...] | None = None,
    language: str = "en",
) -> InlineKeyboardMarkup:
    required = channels if channels is not None else settings.required_channels
    rows = [
        [
            InlineKeyboardButton(
                text=translate(language, "join_channel", label=channel.label),
                url=channel.join_url,
            )
        ]
        for channel in required
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=translate(language, "check_subscription"),
                callback_data=SUBSCRIPTION_CHECK_CALLBACK,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_subscription_gate(
    message: Message,
    settings: Settings,
    missing: tuple[RequiredChannel, ...],
    language: str,
) -> None:
    names = ", ".join(channel.label for channel in missing)
    await message.answer(
        translate(language, "join_required", names=names),
        reply_markup=subscription_keyboard(settings, missing, language),
    )


async def show_home_or_gate(
    message: Message,
    bot: Bot,
    settings: Settings,
    language: str,
) -> bool:
    try:
        missing = await find_missing_channels(
            bot=bot,
            user_id=message.from_user.id if message.from_user else 0,
            channels=settings.required_channels,
        )
    except SubscriptionCheckError:
        logger.exception("Unable to check required channel membership")
        await message.answer(translate(language, "membership_error"))
        return False

    if missing:
        await send_subscription_gate(message, settings, missing, language)
        return False

    await message.answer(translate(language, "home"))
    return True


async def require_access(
    message: Message,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    repository: UserRepository,
) -> bool:
    user_id = message.from_user.id if message.from_user else 0
    language = await repository.get_language(user_id)
    if language is None:
        await message.answer(
            translate(None, "choose_language"),
            reply_markup=language_keyboard(),
        )
        return False
    if not await repository.is_verified(user_id):
        await issue_captcha(message, state, settings, language)
        return False

    try:
        missing = await find_missing_channels(
            bot=bot,
            user_id=user_id,
            channels=settings.required_channels,
        )
    except SubscriptionCheckError:
        logger.exception("Unable to check required channel membership")
        await message.answer(translate(language, "membership_error"))
        return False

    if missing:
        await send_subscription_gate(message, settings, missing, language)
        return False
    return True


@router.message(CommandStart())
async def handle_start(
    message: Message,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    repository: UserRepository,
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    language = await repository.get_language(user_id)
    if language is None:
        await message.answer(
            translate(None, "choose_language"),
            reply_markup=language_keyboard(),
        )
        return
    if not await repository.is_verified(user_id):
        await issue_captcha(message, state, settings, language)
        return
    await show_home_or_gate(message, bot, settings, language)


@router.message(Command("language"))
async def handle_language_command(message: Message) -> None:
    await message.answer(
        translate(None, "choose_language"),
        reply_markup=language_keyboard(),
    )


@router.callback_query(F.data.startswith(LANGUAGE_CALLBACK_PREFIX))
async def handle_language_choice(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    repository: UserRepository,
) -> None:
    language = (callback.data or "").removeprefix(LANGUAGE_CALLBACK_PREFIX)
    if language not in LANGUAGES:
        current_language = (
            await repository.get_language(callback.from_user.id)
            if callback.from_user
            else "en"
        )
        await callback.answer(
            translate(current_language, "unsupported_language"),
            show_alert=True,
        )
        return
    if callback.from_user is None:
        await callback.answer()
        return

    await repository.set_language(callback.from_user.id, language)
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    await callback.message.edit_text(
        translate(language, "language_saved"),
        reply_markup=None,
    )

    if not await repository.is_verified(callback.from_user.id):
        await issue_captcha(callback.message, state, settings, language)
        return
    await show_home_or_gate(callback.message, bot, settings, language)


async def process_captcha_answer(
    *,
    answer: int | None,
    message: Message,
    user_id: int,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    repository: UserRepository,
    challenge_id: str | None = None,
    callback: CallbackQuery | None = None,
) -> None:
    language = await repository.get_language(user_id)
    if language is None:
        if callback is not None:
            await callback.answer(translate(None, "choose_language"), show_alert=True)
        await message.answer(
            translate(None, "choose_language"),
            reply_markup=language_keyboard(),
        )
        return

    data = await state.get_data()
    if data.get("captcha_answer") is None:
        if callback is not None:
            await callback.answer(translate(language, "captcha_no_active"), show_alert=True)
        else:
            await message.answer(translate(language, "captcha_no_active"))
        return
    if data.get("captcha_user_id") != user_id:
        if callback is not None:
            await callback.answer(translate(language, "captcha_not_yours"), show_alert=True)
        else:
            await message.answer(translate(language, "captcha_not_yours"))
        return
    if challenge_id is not None and data.get("captcha_challenge_id") != challenge_id:
        await callback.answer(translate(language, "captcha_old_button"), show_alert=True)
        return

    created_at = float(data.get("captcha_created_at", 0))
    if time.time() - created_at > settings.captcha_ttl_seconds:
        if callback is not None:
            await callback.answer(translate(language, "captcha_expired"), show_alert=True)
        else:
            await message.answer(translate(language, "captcha_expired"))
        await issue_captcha(message, state, settings, language)
        return

    if answer != data.get("captcha_answer"):
        attempts = int(data.get("captcha_attempts", 0)) + 1
        if attempts >= CAPTCHA_ATTEMPTS:
            if callback is not None:
                await callback.answer(
                    translate(language, "captcha_too_many"),
                    show_alert=True,
                )
            else:
                await message.answer(translate(language, "captcha_too_many"))
            await issue_captcha(message, state, settings, language)
            return

        await state.update_data(captcha_attempts=attempts)
        wrong_message = translate(
            language,
            "captcha_wrong",
            attempts=CAPTCHA_ATTEMPTS - attempts,
        )
        if callback is not None:
            await callback.answer(wrong_message)
        else:
            await message.answer(wrong_message)
        return

    await repository.mark_verified(user_id)
    await state.clear()
    if callback is not None:
        await callback.answer(translate(language, "captcha_passed"))
    else:
        await message.answer(translate(language, "captcha_passed"))
    await show_home_or_gate(message, bot, settings, language)


@router.message(CaptchaState.waiting_for_answer)
async def handle_captcha_answer(
    message: Message,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    repository: UserRepository,
) -> None:
    try:
        answer = int((message.text or "").strip())
    except ValueError:
        answer = None

    user_id = message.from_user.id if message.from_user else 0
    await process_captcha_answer(
        answer=answer,
        message=message,
        user_id=user_id,
        state=state,
        bot=bot,
        settings=settings,
        repository=repository,
    )


@router.callback_query(F.data.startswith(CAPTCHA_CALLBACK_PREFIX))
async def handle_captcha_button(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    repository: UserRepository,
) -> None:
    if not isinstance(callback.message, Message) or callback.from_user is None:
        await callback.answer()
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        language = (
            await repository.get_language(callback.from_user.id)
            if callback.from_user
            else "en"
        )
        await callback.answer(
            translate(language, "invalid_captcha_button"),
            show_alert=True,
        )
        return
    try:
        answer = int(parts[2])
    except ValueError:
        answer = None

    await process_captcha_answer(
        answer=answer,
        message=callback.message,
        user_id=callback.from_user.id,
        state=state,
        bot=bot,
        settings=settings,
        repository=repository,
        challenge_id=parts[1],
        callback=callback,
    )


@router.callback_query(F.data == SUBSCRIPTION_CHECK_CALLBACK)
async def handle_subscription_check(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    repository: UserRepository,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return

    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    language = await repository.get_language(callback.from_user.id)
    if language is None:
        await callback.answer(translate(None, "choose_language"), show_alert=True)
        await callback.message.answer(
            translate(None, "choose_language"),
            reply_markup=language_keyboard(),
        )
        return
    if not await repository.is_verified(callback.from_user.id):
        await callback.answer(translate(language, "captcha_required"), show_alert=True)
        await issue_captcha(callback.message, state, settings, language)
        return

    try:
        missing = await find_missing_channels(
            bot=bot,
            user_id=callback.from_user.id,
            channels=settings.required_channels,
        )
    except SubscriptionCheckError:
        logger.exception("Unable to check required channel membership")
        await callback.answer(
            translate(language, "membership_error"),
            show_alert=True,
        )
        return

    if missing:
        await callback.answer(
            translate(language, "membership_missing"),
            show_alert=True,
        )
        await send_subscription_gate(callback.message, settings, missing, language)
        return

    await callback.answer(translate(language, "membership_confirmed"))
    await callback.message.answer(translate(language, "home"))

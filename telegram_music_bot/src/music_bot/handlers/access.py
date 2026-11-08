from __future__ import annotations

import logging
import secrets
import time

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from music_bot.config import RequiredChannel, Settings
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


async def issue_captcha(
    message: Message,
    state: FSMContext,
    settings: Settings,
) -> None:
    left = secrets.randbelow(9) + 2
    right = secrets.randbelow(9) + 2
    await state.set_state(CaptchaState.waiting_for_answer)
    await state.set_data(
        {
            "captcha_answer": left + right,
            "captcha_created_at": time.time(),
            "captcha_attempts": 0,
        }
    )
    await message.answer(
        "Before using music search, solve this quick check:\n\n"
        f"<b>{left} + {right} = ?</b>\n"
        f"Reply with the number within {settings.captcha_ttl_seconds} seconds."
    )


def subscription_keyboard(
    settings: Settings,
    channels: tuple[RequiredChannel, ...] | None = None,
) -> InlineKeyboardMarkup:
    required = channels if channels is not None else settings.required_channels
    rows = [
        [
            InlineKeyboardButton(
                text=f"Join {channel.label}",
                url=channel.join_url,
            )
        ]
        for channel in required
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="I've joined — check",
                callback_data=SUBSCRIPTION_CHECK_CALLBACK,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_subscription_gate(
    message: Message,
    settings: Settings,
    missing: tuple[RequiredChannel, ...],
) -> None:
    names = ", ".join(channel.label for channel in missing)
    await message.answer(
        "Join the required channel(s) to use music search:\n"
        f"<b>{names}</b>\n\n"
        "After joining, tap “I've joined — check”.",
        reply_markup=subscription_keyboard(settings, missing),
    )


async def show_home_or_gate(
    message: Message,
    bot: Bot,
    settings: Settings,
) -> bool:
    try:
        missing = await find_missing_channels(
            bot=bot,
            user_id=message.from_user.id if message.from_user else 0,
            channels=settings.required_channels,
        )
    except SubscriptionCheckError:
        logger.exception("Unable to check required channel membership")
        await message.answer(
            "I couldn't check channel membership. Please contact the bot "
            "administrator and ask them to confirm I can access every "
            "required channel."
        )
        return False

    if missing:
        await send_subscription_gate(message, settings, missing)
        return False

    await message.answer(
        "You're all set. Send a song title or artist name to search.\n"
        "You can also use <code>/search artist or song</code>."
    )
    return True


async def require_access(
    message: Message,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    repository: UserRepository,
) -> bool:
    user_id = message.from_user.id if message.from_user else 0
    if not await repository.is_verified(user_id):
        await issue_captcha(message, state, settings)
        return False

    try:
        missing = await find_missing_channels(
            bot=bot,
            user_id=user_id,
            channels=settings.required_channels,
        )
    except SubscriptionCheckError:
        logger.exception("Unable to check required channel membership")
        await message.answer(
            "I couldn't check channel membership. Please contact the bot "
            "administrator and ask them to confirm I can access every "
            "required channel."
        )
        return False

    if missing:
        await send_subscription_gate(message, settings, missing)
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
    if not await repository.is_verified(user_id):
        await issue_captcha(message, state, settings)
        return
    await show_home_or_gate(message, bot, settings)


@router.message(CaptchaState.waiting_for_answer)
async def handle_captcha_answer(
    message: Message,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    repository: UserRepository,
) -> None:
    data = await state.get_data()
    created_at = float(data.get("captcha_created_at", 0))
    if time.time() - created_at > settings.captcha_ttl_seconds:
        await issue_captcha(message, state, settings)
        return

    try:
        answer = int((message.text or "").strip())
    except ValueError:
        answer = None

    if answer != data.get("captcha_answer"):
        attempts = int(data.get("captcha_attempts", 0)) + 1
        if attempts >= CAPTCHA_ATTEMPTS:
            await issue_captcha(message, state, settings)
            await message.answer("That challenge expired after too many attempts.")
            return
        await state.update_data(captcha_attempts=attempts)
        await message.answer(
            f"That answer wasn't correct. Try again "
            f"({CAPTCHA_ATTEMPTS - attempts} attempt(s) left)."
        )
        return

    user_id = message.from_user.id if message.from_user else 0
    await repository.mark_verified(user_id)
    await state.clear()
    await message.answer("CAPTCHA passed.")
    await show_home_or_gate(message, bot, settings)


@router.callback_query(F.data == SUBSCRIPTION_CHECK_CALLBACK)
async def handle_subscription_check(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    repository: UserRepository,
) -> None:
    if callback.from_user is None or not await repository.is_verified(
        callback.from_user.id
    ):
        await callback.answer("Please complete the CAPTCHA first.", show_alert=True)
        if isinstance(callback.message, Message):
            await issue_captcha(callback.message, state, settings)
        return

    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    try:
        missing = await find_missing_channels(
            bot=bot,
            user_id=callback.from_user.id,
            channels=settings.required_channels,
        )
    except SubscriptionCheckError:
        logger.exception("Unable to check required channel membership")
        await callback.answer("Membership could not be checked.", show_alert=True)
        await callback.message.answer(
            "I couldn't check channel membership. Please contact the bot "
            "administrator and ask them to confirm I can access every "
            "required channel."
        )
        return

    if missing:
        await callback.answer("Some required channels are still missing.", show_alert=True)
        await send_subscription_gate(callback.message, settings, missing)
        return

    await callback.answer("Subscription confirmed.")
    await callback.message.answer(
        "You're all set. Send a song title or artist name to search.\n"
        "You can also use <code>/search artist or song</code>."
    )

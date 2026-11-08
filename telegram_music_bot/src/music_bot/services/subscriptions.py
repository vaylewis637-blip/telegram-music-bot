from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from music_bot.config import RequiredChannel


class SubscriptionCheckError(RuntimeError):
    """Raised when Telegram refuses a required-channel membership check."""


async def find_missing_channels(
    bot: Bot,
    user_id: int,
    channels: tuple[RequiredChannel, ...],
) -> tuple[RequiredChannel, ...]:
    missing: list[RequiredChannel] = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(
                chat_id=channel.chat_id,
                user_id=user_id,
            )
        except TelegramAPIError as error:
            raise SubscriptionCheckError(
                f"Telegram could not check membership for {channel.label}."
            ) from error

        is_member = member.status in {"creator", "administrator", "member"}
        if member.status == "restricted":
            is_member = bool(getattr(member, "is_member", False))
        if not is_member:
            missing.append(channel)
    return tuple(missing)

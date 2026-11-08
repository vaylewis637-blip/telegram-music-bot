from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class ConfigurationError(ValueError):
    """Raised when required bot settings are missing or invalid."""


@dataclass(frozen=True, slots=True)
class RequiredChannel:
    chat_id: str | int
    join_url: str
    label: str


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    required_channels: tuple[RequiredChannel, ...]
    database_path: Path
    search_results_limit: int
    captcha_ttl_seconds: int
    itunes_country: str

    @classmethod
    def from_env(cls) -> Settings:
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not bot_token:
            raise ConfigurationError(
                "Set TELEGRAM_BOT_TOKEN in the project's Secrets."
            )

        channel_values = _split_csv(os.getenv("REQUIRED_CHANNELS", ""))
        if not channel_values:
            raise ConfigurationError(
                "Set REQUIRED_CHANNELS to the channel handles or chat IDs "
                "that users must join."
            )

        join_links = _split_csv(os.getenv("REQUIRED_CHANNEL_LINKS", ""))
        if join_links and len(join_links) != len(channel_values):
            raise ConfigurationError(
                "REQUIRED_CHANNEL_LINKS must contain one link per "
                "REQUIRED_CHANNELS entry, in the same order."
            )

        channels: list[RequiredChannel] = []
        for index, value in enumerate(channel_values):
            chat_id, label = _parse_chat_id(value, index)
            join_url = join_links[index] if join_links else ""
            if not join_url and isinstance(chat_id, str):
                join_url = f"https://t.me/{chat_id.removeprefix('@')}"
            if not join_url:
                raise ConfigurationError(
                    f"Channel {value!r} is a numeric chat ID; provide its "
                    "invite URL in REQUIRED_CHANNEL_LINKS."
                )
            if not _is_https_url(join_url):
                raise ConfigurationError(
                    f"Join link for channel {value!r} must be an https URL."
                )
            channels.append(
                RequiredChannel(
                    chat_id=chat_id,
                    join_url=join_url,
                    label=label,
                )
            )

        results_limit = _positive_int(
            "SEARCH_RESULTS_LIMIT",
            os.getenv("SEARCH_RESULTS_LIMIT", "5"),
        )
        if not 1 <= results_limit <= 10:
            raise ConfigurationError("SEARCH_RESULTS_LIMIT must be from 1 to 10.")

        captcha_ttl = _positive_int(
            "CAPTCHA_TTL_SECONDS",
            os.getenv("CAPTCHA_TTL_SECONDS", "300"),
        )
        if captcha_ttl < 30:
            raise ConfigurationError("CAPTCHA_TTL_SECONDS must be at least 30.")

        country = os.getenv("ITUNES_COUNTRY", "US").strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", country):
            raise ConfigurationError("ITUNES_COUNTRY must be a two-letter code.")

        return cls(
            bot_token=bot_token,
            required_channels=tuple(channels),
            database_path=Path(
                os.getenv("DATABASE_PATH", "data/music_bot.sqlite3")
            ).expanduser(),
            search_results_limit=results_limit,
            captcha_ttl_seconds=captcha_ttl,
            itunes_country=country,
        )


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_chat_id(value: str, index: int) -> tuple[str | int, str]:
    if value.startswith("@") and re.fullmatch(r"@[A-Za-z0-9_]{5,}", value):
        return value, value
    if re.fullmatch(r"-?\d+", value):
        return int(value), f"Channel {index + 1}"
    raise ConfigurationError(
        f"Invalid channel {value!r}; use a public @username or numeric chat ID."
    )


def _positive_int(name: str, value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be an integer.") from error
    if parsed <= 0:
        raise ConfigurationError(f"{name} must be greater than zero.")
    return parsed


def _is_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)

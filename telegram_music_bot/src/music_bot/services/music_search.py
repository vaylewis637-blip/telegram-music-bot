from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

import aiohttp

from music_bot.models import Track

logger = logging.getLogger(__name__)


class MusicSearchError(RuntimeError):
    """Raised when the public music search API cannot be reached."""


class MusicSearch:
    def __init__(self, session: aiohttp.ClientSession, country: str) -> None:
        self._session = session
        self._country = country

    async def search(self, query: str, limit: int) -> list[Track]:
        try:
            async with self._session.get(
                "https://itunes.apple.com/search",
                params={
                    "term": query,
                    "entity": "song",
                    "limit": limit,
                    "country": self._country,
                },
            ) as response:
                response.raise_for_status()
                payload: Any = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            raise MusicSearchError("The iTunes Search API request failed.") from error
        except (ValueError, TypeError) as error:
            raise MusicSearchError("The iTunes Search API returned invalid data.") from error

        if not isinstance(payload, dict):
            raise MusicSearchError("The iTunes Search API returned an unexpected response.")

        results = payload.get("results", [])
        if not isinstance(results, list):
            raise MusicSearchError("The iTunes Search API returned an unexpected result list.")

        tracks: list[Track] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            title = item.get("trackName")
            artist = item.get("artistName")
            track_url = item.get("trackViewUrl")
            if not all(
                isinstance(value, str) and value.strip()
                for value in (title, artist, track_url)
            ):
                continue
            if not _is_https_url(track_url):
                continue
            tracks.append(
                Track(
                    title=title.strip(),
                    artist=artist.strip(),
                    album=str(item.get("collectionName") or "").strip(),
                    track_url=track_url.strip(),
                    preview_url=_optional_string(item.get("previewUrl")),
                )
            )
        return tracks[:limit]


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and _is_https_url(value):
        return value
    return None


def _is_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)

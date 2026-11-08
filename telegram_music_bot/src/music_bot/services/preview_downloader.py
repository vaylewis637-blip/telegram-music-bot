from __future__ import annotations

import asyncio
import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

import aiohttp

MAX_PREVIEW_BYTES = 15 * 1024 * 1024
ALLOWED_CONTENT_TYPES = ("audio/", "application/octet-stream")


class PreviewDownloadError(RuntimeError):
    """Raised when a preview cannot be safely downloaded."""


class PreviewDownloader:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def download(self, url: str) -> bytes:
        _validate_apple_preview_url(url)
        try:
            async with self._session.get(url, allow_redirects=True) as response:
                response.raise_for_status()
                _validate_apple_preview_url(str(response.url))

                content_type = (
                    response.headers.get("Content-Type", "")
                    .split(";", maxsplit=1)[0]
                    .strip()
                    .lower()
                )
                if not content_type.startswith(ALLOWED_CONTENT_TYPES):
                    raise PreviewDownloadError(
                        "The preview endpoint did not return an audio file."
                    )
                if response.content_length and response.content_length > MAX_PREVIEW_BYTES:
                    raise PreviewDownloadError("The preview file is too large.")

                chunks: list[bytes] = []
                total_bytes = 0
                async for chunk in response.content.iter_chunked(64 * 1024):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_PREVIEW_BYTES:
                        raise PreviewDownloadError("The preview file is too large.")
                    chunks.append(chunk)
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            raise PreviewDownloadError("The preview download failed.") from error

        audio = b"".join(chunks)
        if not audio:
            raise PreviewDownloadError("The preview file was empty.")
        return audio

    @staticmethod
    def filename_for(url: str) -> str:
        suffix = PurePosixPath(urlsplit(url).path).suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
            suffix = ".m4a"
        return f"music-preview{suffix}"


def _validate_apple_preview_url(url: str) -> None:
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not hostname
        or not (hostname == "itunes.apple.com" or hostname.endswith(".itunes.apple.com"))
        or parsed.username
        or parsed.password
    ):
        raise PreviewDownloadError("Only HTTPS Apple Music preview URLs are supported.")

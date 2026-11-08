from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Track:
    title: str
    artist: str
    album: str
    preview_url: str | None

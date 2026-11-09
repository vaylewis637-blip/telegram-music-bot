from __future__ import annotations

import io
import re
from pathlib import Path

from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, ID3NoHeaderError
from PIL import Image, UnidentifiedImageError
from pydub import AudioSegment

MAX_AUDIO_BYTES = 15 * 1024 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class AudioEditError(ValueError):
    """Audio cannot be converted or edited with the available system tools."""


def to_mp3(audio: bytes, source_format: str = "m4a") -> bytes:
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise AudioEditError("Размер аудиофайла недопустим.")
    try:
        segment = AudioSegment.from_file(io.BytesIO(audio), format=source_format)
        output = io.BytesIO()
        segment.export(output, format="mp3", bitrate="192k")
        return output.getvalue()
    except (OSError, RuntimeError, ValueError) as error:
        raise AudioEditError(
            "Не удалось обработать аудио. Проверьте, что FFmpeg установлен."
        ) from error


def edit_speed(audio: bytes, speed: float) -> bytes:
    if speed not in {0.75, 0.9, 1.25}:
        raise AudioEditError("Выберите скорость из предложенного списка.")
    segment = _load_mp3(audio)
    changed = segment._spawn(
        segment.raw_data,
        overrides={"frame_rate": int(segment.frame_rate * speed)},
    ).set_frame_rate(segment.frame_rate)
    return _export_mp3(changed)


def trim_audio(audio: bytes, start_ms: int, end_ms: int) -> bytes:
    segment = _load_mp3(audio)
    if start_ms < 0 or end_ms <= start_ms or end_ms > len(segment):
        raise AudioEditError(
            "Время должно быть в пределах файла, а конец — позже начала."
        )
    return _export_mp3(segment[start_ms:end_ms])


def normalize_cover(image_bytes: bytes) -> bytes:
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise AudioEditError("Изображение пустое или превышает 10 МБ.")
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image = image.convert("RGB")
            image.thumbnail((1000, 1000))
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=88, optimize=True)
            return output.getvalue()
    except (OSError, UnidentifiedImageError) as error:
        raise AudioEditError("Не удалось прочитать изображение. Пришлите фото в JPG или PNG.") from error


def apply_metadata(
    audio: bytes,
    title: str,
    artist: str,
    album: str,
    cover: bytes | None = None,
) -> bytes:
    output = io.BytesIO(audio)
    try:
        try:
            tags = ID3(fileobj=io.BytesIO(audio))
        except ID3NoHeaderError:
            tags = ID3()
        tags.delall("TIT2")
        tags.delall("TPE1")
        tags.delall("TALB")
        tags.add(TIT2(encoding=3, text=[title]))
        tags.add(TPE1(encoding=3, text=[artist]))
        tags.add(TALB(encoding=3, text=[album]))
        tags.delall("APIC")
        if cover:
            tags.add(
                APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,
                    desc="Обложка",
                    data=cover,
                )
            )
        result = io.BytesIO()
        tags.save(result, v2_version=3)
        id3_data = result.getvalue()
        # ID3 tags precede MPEG frames. Strip existing tags before writing fresh tags.
        frame_data = _strip_id3(audio)
        return id3_data + frame_data
    except (OSError, ValueError, TypeError) as error:
        raise AudioEditError("Не удалось записать теги и обложку в MP3.") from error


def parse_time_range(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d{1,4}):(\d{2})\s*[—–-]\s*(\d{1,4}):(\d{2})\s*", value)
    if not match:
        raise AudioEditError("Формат времени: мм:сс — мм:сс, например 0:30 — 1:15.")
    start_min, start_sec, end_min, end_sec = map(int, match.groups())
    if start_sec > 59 or end_sec > 59:
        raise AudioEditError("Секунды должны быть от 00 до 59.")
    return (start_min * 60 + start_sec) * 1000, (end_min * 60 + end_sec) * 1000


def save_audio(audio: bytes, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(audio)


def _load_mp3(audio: bytes) -> AudioSegment:
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise AudioEditError("Размер аудиофайла недопустим.")
    try:
        return AudioSegment.from_file(io.BytesIO(audio), format="mp3")
    except (OSError, RuntimeError, ValueError) as error:
        raise AudioEditError("Не удалось декодировать MP3. Проверьте установку FFmpeg.") from error


def _export_mp3(segment: AudioSegment) -> bytes:
    output = io.BytesIO()
    try:
        segment.export(output, format="mp3", bitrate="192k")
    except (OSError, RuntimeError, ValueError) as error:
        raise AudioEditError("Не удалось обработать MP3. Проверьте установку FFmpeg.") from error
    return output.getvalue()


def _strip_id3(audio: bytes) -> bytes:
    if len(audio) >= 10 and audio[:3] == b"ID3":
        size = ((audio[6] & 0x7F) << 21) | ((audio[7] & 0x7F) << 14) | ((audio[8] & 0x7F) << 7) | (audio[9] & 0x7F)
        return audio[10 + size:]
    return audio

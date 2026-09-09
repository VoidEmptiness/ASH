"""Работа с аудиофайлами: метаданные, проверки типов, имена (бывший блок metadata из utils.py)."""
import re
from pathlib import Path
from mutagen import File as MutagenFile

from ..config import SUPPORTED_EXTENSIONS


def extract_metadata(filepath: Path) -> dict:
    """Извлекает метаданные из аудиофайла."""
    try:
        audio = MutagenFile(str(filepath), easy=True)
        if audio is None:
            return {}

        duration = 0.0
        if hasattr(audio, "info") and hasattr(audio.info, "length"):
            duration = float(audio.info.length)

        bitrate = None
        if hasattr(audio, "info") and hasattr(audio.info, "bitrate"):
            bitrate = int(audio.info.bitrate)

        def get_tag(key, default=""):
            vals = audio.get(key)
            if vals:
                return str(vals[0])
            return default

        title = get_tag("title") or filepath.stem
        artist = get_tag("artist") or "Unknown Artist"
        album = get_tag("album") or "Unknown Album"
        date = get_tag("date") or get_tag("year") or None
        genre = get_tag("genre") or None

        year = None
        if date:
            year = str(date)[:4]

        return {
            "title": title,
            "artist": artist,
            "album": album,
            "duration": duration,
            "year": year,
            "genre": genre,
            "bitrate": bitrate,
        }
    except Exception as e:
        print(f"[ASH] metadata error {filepath}: {e}")
        return {
            "title": filepath.stem,
            "artist": "Unknown Artist",
            "album": "Unknown Album",
            "duration": 0.0,
            "year": None,
            "genre": None,
            "bitrate": None,
        }


def is_supported_file(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def format_duration(seconds: float) -> str:
    if not seconds:
        return "0:00"
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


def safe_filename(name: str) -> str:
    keep = "-_.() "
    return "".join(c for c in name if c.isalnum() or c in keep).strip()


def safe_folder_name(name: str) -> str:
    # для папок плейлистов: убираем слэши, оставляем буквы/цифры/пробел/дефис/подчеркивание
    keep = "-_ "
    cleaned = "".join(c for c in name if c.isalnum() or c in keep).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = "playlist"
    return cleaned[:60]

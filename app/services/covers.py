"""Извлечение и хранение обложек треков/альбомов.

Источники (по приоритету):
1. Встроенная обложка в тегах (ID3 APIC, FLAC pictures, MP4 covr, Vorbis METADATA_BLOCK_PICTURE, ASF WM/Picture)
2. Файл-обложка рядом с треком: cover.jpg/png/webp, folder.jpg, front.jpg, album.jpg ...

Хранение: DATA_DIR/covers/{track_id}.{ext} и album_{album_id}.{ext}.
Если Pillow доступен — ресайзим до 600px и конвертируем в JPEG для экономии.
Без Pillow — сохраняем байты как есть.
"""
import base64
from pathlib import Path

from ..config import COVERS_DIR

FOLDER_COVER_NAMES = [
    "cover.jpg", "cover.jpeg", "cover.png", "cover.webp",
    "folder.jpg", "folder.jpeg", "folder.png",
    "front.jpg", "front.png", "album.jpg", "album.png",
    "artwork.jpg", "artwork.png",
]

PLACEHOLDER_MIME = "image/svg+xml"


def _guess_ext(mime: str) -> str:
    m = (mime or "").lower()
    if "png" in m:
        return ".png"
    if "webp" in m:
        return ".webp"
    if "gif" in m:
        return ".gif"
    return ".jpg"


def extract_embedded_cover(filepath: Path):
    """Возвращает (bytes, mime) или (None, None)."""
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(str(filepath))
        if audio is None or not hasattr(audio, "tags") or audio.tags is None:
            return None, None
        tags = audio.tags

        # --- MP3 / ID3: APIC ---
        try:
            from mutagen.id3 import APIC

            apics = tags.getall("APIC") if hasattr(tags, "getall") else []
            if apics:
                # предпочитаем front cover (type 3), иначе первую
                front = [p for p in apics if getattr(p, "type", 3) == 3]
                pic = front[0] if front else apics[0]
                data = getattr(pic, "data", None)
                mime = getattr(pic, "mime", "image/jpeg") or "image/jpeg"
                if data:
                    return bytes(data), mime
        except Exception:
            pass

        # --- MP4/M4A: covr ---
        try:
            if "covr" in tags and tags["covr"]:
                blob = bytes(tags["covr"][0])
                # эвристика mime по сигнатуре
                if blob[:8].startswith(b"\x89PNG"):
                    return blob, "image/png"
                if blob[:3] == b"GIF":
                    return blob, "image/gif"
                if blob[:4] == b"RIFF":
                    return blob, "image/webp"
                return blob, "image/jpeg"
        except Exception:
            pass

        # --- FLAC: pictures ---
        try:
            pics = getattr(audio, "pictures", None)
            if pics:
                pic = pics[0]
                return bytes(pic.data), (pic.mime or "image/jpeg")
        except Exception:
            pass

        # --- Vorbis (ogg/opus): METADATA_BLOCK_PICTURE (base64) ---
        try:
            mbp = tags.get("METADATA_BLOCK_PICTURE") or tags.get("metadata_block_picture")
            if mbp:
                from mutagen.flac import Picture

                raw = base64.b64decode(str(mbp[0]))
                pic = Picture(raw)
                return bytes(pic.data), (pic.mime or "image/jpeg")
            # старый вариант: COVERART
            ca = tags.get("COVERART") or tags.get("coverart")
            if ca:
                blob = base64.b64decode(str(ca[0]))
                return blob, "image/jpeg"
        except Exception:
            pass

        # --- WMA/ASF: WM/Picture ---
        try:
            for key in ("WM/Picture", "WM/Picture "):
                if key in tags:
                    for item in tags[key]:
                        data = getattr(item, "value", None) or getattr(item, "data", None)
                        if data and len(bytes(data)) > 100:
                            return bytes(data), getattr(item, "mime", "image/jpeg") or "image/jpeg"
        except Exception:
            pass

        # --- Generic fallback: ищем объект с .data у тегов ---
        try:
            for v in tags.values():
                items = v if isinstance(v, list) else [v]
                for it in items:
                    d = getattr(it, "data", None)
                    m = getattr(it, "mime", None)
                    if isinstance(d, (bytes, bytearray)) and len(d) > 200:
                        return bytes(d), m or "image/jpeg"
        except Exception:
            pass
    except Exception as e:
        print(f"[ASH] cover extract error {filepath}: {e}")
    return None, None


def find_folder_cover(filepath: Path):
    """Ищет cover/folder/front рядом с файлом. Возвращает Path или None."""
    try:
        parent = filepath.parent
        if not parent.exists():
            return None
        for name in FOLDER_COVER_NAMES:
            cand = parent / name
            if cand.is_file() and cand.stat().st_size > 0:
                return cand
        # fallback: любой *.jpg/png в папке с именем cover*/folder*/front*/album*
        for cand in parent.glob("*"):
            if not cand.is_file():
                continue
            low = cand.name.lower()
            if cand.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                if low.startswith(("cover", "folder", "front", "album", "artwork")):
                    return cand
    except Exception:
        pass
    return None


def _normalize_image(data: bytes, mime: str, max_size: int = 600) -> tuple[bytes, str]:
    """Ресайз + JPEG через Pillow если доступен, иначе как есть."""
    try:
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(data))
        if img.mode in ("RGBA", "LA", "PA"):
            bg = Image.new("RGB", img.size, (26, 26, 28))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=85, optimize=True)
        return out.getvalue(), "image/jpeg"
    except ImportError:
        return data, mime or "image/jpeg"
    except Exception as e:
        print(f"[ASH] cover normalize error: {e}")
        return data, mime or "image/jpeg"


def save_cover_for_track(track_id: int, audio_path: Path) -> str | None:
    """Извлекает обложку для трека и сохраняет в COVERS_DIR. Возвращает имя файла или None."""
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    data, mime = extract_embedded_cover(audio_path)
    if not data:
        folder_img = find_folder_cover(audio_path)
        if folder_img:
            try:
                data = folder_img.read_bytes()
                import mimetypes

                mime = mimetypes.guess_type(str(folder_img))[0] or "image/jpeg"
            except Exception:
                data = None
    if not data:
        return None
    data, mime = _normalize_image(data, mime)
    ext = _guess_ext(mime)
    # чистим старые варианты расширений этого трека
    for old in COVERS_DIR.glob(f"{track_id}.*"):
        try:
            old.unlink()
        except Exception:
            pass
    dest = COVERS_DIR / f"{track_id}{ext}"
    try:
        dest.write_bytes(data)
        return dest.name
    except Exception as e:
        print(f"[ASH] cover save error: {e}")
        return None


def save_cover_for_album(album_id: int, src_cover_name: str | None) -> str | None:
    """Копирует обложку трека как обложку альбома. Возвращает имя файла или None."""
    if not src_cover_name:
        return None
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    src = COVERS_DIR / src_cover_name
    if not src.is_file():
        return None
    ext = src.suffix or ".jpg"
    dest = COVERS_DIR / f"album_{album_id}{ext}"
    # чистим старые
    for old in COVERS_DIR.glob(f"album_{album_id}.*"):
        if old != dest:
            try:
                old.unlink()
            except Exception:
                pass
    try:
        if src.resolve() != dest.resolve():
            dest.write_bytes(src.read_bytes())
        return dest.name
    except Exception as e:
        print(f"[ASH] album cover save error: {e}")
        return None


def cover_file_response_path(stored: str | None) -> Path | None:
    if not stored:
        return None
    p = COVERS_DIR / Path(stored).name  # защита от traversal
    return p if p.is_file() else None


def placeholder_svg(letter: str = "♪") -> bytes:
    l = (letter or "♪").strip()[:2].upper() or "♪"
    l = l.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300"><rect width="300" height="300" rx="24" fill="#1a1a1c"/><rect x="8" y="8" width="284" height="284" rx="18" fill="none" stroke="#2a2a2c" stroke-width="2"/><text x="150" y="178" font-family="monospace" font-size="96" fill="#6b6a68" text-anchor="middle">{l}</text></svg>""".encode()

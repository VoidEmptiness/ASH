"""Работа с файлами и папками плейлистов (аналог services/storage.py в Video-Library)."""
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import MUSIC_DIR, LIKED_SONGS_NAME
from ..models import Playlist
from ..database import SessionLocal
from .metadata import safe_folder_name


def get_playlist_folder(playlist: Playlist, ensure_exists: bool = True) -> Path:
    """Возвращает Path папки плейлиста, создаёт её если нужно."""
    if playlist.folder:
        folder = MUSIC_DIR / playlist.folder
    else:
        base = safe_folder_name(playlist.name)
        candidate = base
        counter = 1
        db = SessionLocal()
        try:
            existing = {p.folder for p in db.query(Playlist).all() if p.folder}
            while candidate in existing:
                counter += 1
                candidate = f"{base}_{counter}"
        finally:
            db.close()
        playlist.folder = candidate
        try:
            db2 = SessionLocal()
            pl2 = db2.query(Playlist).filter(Playlist.id == playlist.id).first()
            if pl2:
                pl2.folder = candidate
                db2.commit()
            db2.close()
        except Exception:
            pass
        folder = MUSIC_DIR / candidate
    if ensure_exists:
        folder.mkdir(parents=True, exist_ok=True)
    return folder


def ensure_playlist_folders(db: Session):
    """Для существующих плейлистов без folder — создать. Пропускаем виртуальные (Liked Songs)."""
    for pl in db.query(Playlist).all():
        if pl.name == LIKED_SONGS_NAME:
            continue
        if not pl.folder:
            base = safe_folder_name(pl.name)
            candidate = base
            counter = 1
            existing = {p.folder for p in db.query(Playlist).all() if p.folder}
            while candidate in existing:
                counter += 1
                candidate = f"{base}_{counter}"
            pl.folder = candidate
            Path(MUSIC_DIR / candidate).mkdir(parents=True, exist_ok=True)
    db.commit()


def file_iterator(path: Path, start: int = 0, end: int = None, chunk_size: int = 8192):
    with open(path, "rb") as f:
        f.seek(start)
        remaining = (end - start + 1) if end is not None else None
        while True:
            to_read = chunk_size if remaining is None else min(chunk_size, remaining)
            data = f.read(to_read)
            if not data:
                break
            if remaining is not None:
                remaining -= len(data)
            yield data


def resolve_track_path(track) -> Path:
    """Возвращает реальный путь к файлу трека (filepath или MUSIC_DIR/filename)."""
    p = Path(track.filepath)
    if not p.exists():
        p = MUSIC_DIR / track.filename
    return p

"""Сканирование фонотеки и синхронизация плейлистов с папками."""
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import MUSIC_DIR, LIKED_SONGS_NAME, DEFAULT_PLAYLIST_NAME
from ..models import Track, Playlist, Album
from .albums import get_or_create_album
from .metadata import is_supported_file, extract_metadata
from .storage import ensure_playlist_folders


def ensure_playlists_from_folders(db: Session):
    """Создаёт плейлисты для каждой папки в MUSIC_DIR, если их ещё нет в БД."""
    try:
        for folder_path in MUSIC_DIR.iterdir():
            if not folder_path.is_dir():
                continue
            if folder_path.name.startswith("."):
                continue
            rel = folder_path.name
            if db.query(Playlist).filter(Playlist.folder == rel).first():
                continue
            existing_by_name = db.query(Playlist).filter(Playlist.name == rel).first()
            if existing_by_name and not existing_by_name.folder:
                existing_by_name.folder = rel
                continue
            candidate_name = rel
            counter = 1
            existing_names = {p.name for p in db.query(Playlist).all()}
            while candidate_name in existing_names:
                counter += 1
                candidate_name = f"{rel}_{counter}"
            pl = Playlist(name=candidate_name, description=f"Папка {rel}", cover_color="#2a2a2a", folder=rel)
            db.add(pl)
        db.commit()
        # cleanup: удаляем плейлисты чьи папки удалены вручную с диска (кроме системных)
        for pl in db.query(Playlist).all():
            if pl.folder and pl.name not in (DEFAULT_PLAYLIST_NAME, LIKED_SONGS_NAME):
                if not (MUSIC_DIR / pl.folder).exists():
                    db.delete(pl)
        db.commit()
    except Exception as e:
        print(f"[ASH] ensure_playlists_from_folders error: {e}")


def sync_playlist_folder_tracks(db: Session):
    """Синхронизирует содержимое плейлистов с файлами в их папках (добавляет недостающие)."""
    try:
        for pl in db.query(Playlist).all():
            if not pl.folder:
                continue
            folder = pl.folder
            if pl.name in (DEFAULT_PLAYLIST_NAME, LIKED_SONGS_NAME):
                continue
            prefix = folder + "/"
            tracks_in_folder = db.query(Track).filter(Track.filename.startswith(prefix)).all()
            existing_ids = {t.id for t in pl.tracks}
            for t in tracks_in_folder:
                if t.id not in existing_ids:
                    pl.tracks.append(t)
        db.commit()
    except Exception as e:
        print(f"[ASH] sync_playlist_folder_tracks error: {e}")


def scan_music_folder(db: Session):
    """Сканирует MUSIC_DIR и добавляет недостающие треки в БД."""
    ensure_playlist_folders(db)
    ensure_playlists_from_folders(db)
    existing = {t.filename for t in db.query(Track).all()}
    added = 0
    for f in MUSIC_DIR.rglob("*"):
        if not f.is_file() or not is_supported_file(f):
            continue
        rel = str(f.relative_to(MUSIC_DIR))
        if rel in existing:
            continue
        if db.query(Track).filter(Track.filepath == str(f)).first():
            continue
        meta = extract_metadata(f)
        try:
            stat = f.stat()
            size = stat.st_size
        except Exception:
            size = 0
        album_obj = get_or_create_album(db, meta.get("album", "Unknown Album"), meta.get("artist", "Unknown Artist"), meta.get("year"), meta.get("genre"))
        track = Track(
            title=meta.get("title", f.stem),
            artist=meta.get("artist", "Unknown Artist"),
            album=meta.get("album", "Unknown Album"),
            album_id=album_obj.id if album_obj else None,
            duration=meta.get("duration", 0.0),
            filename=rel,
            filepath=str(f),
            file_size=size,
            bitrate=meta.get("bitrate"),
            year=meta.get("year"),
            genre=meta.get("genre"),
        )
        db.add(track)
        added += 1
    # remove missing files — проверяем и по абсолютному пути и по относительному (для совместимости Docker/host)
    for t in db.query(Track).all():
        exists = Path(t.filepath).exists() or (MUSIC_DIR / t.filename).exists()
        if not Path(t.filepath).exists() and (MUSIC_DIR / t.filename).exists():
            t.filepath = str(MUSIC_DIR / t.filename)
        if not exists:
            db.delete(t)
    db.commit()
    # чистим пустые альбомы без треков — одним запросом
    empty = db.query(Album).filter(~Album.tracks.any()).all()
    if empty:
        for alb in empty:
            db.delete(alb)
        db.commit()
    ensure_playlists_from_folders(db)
    sync_playlist_folder_tracks(db)
    return added

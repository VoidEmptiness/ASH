from pathlib import Path

from sqlalchemy.orm import Session

from ..config import MUSIC_DIR, LIKED_SONGS_NAME, DEFAULT_PLAYLIST_NAME
from ..models import Track, Playlist, Album
from .albums import get_or_create_album
from .metadata import is_supported_file, extract_metadata
from .covers import save_cover_for_track, save_cover_for_album
from .storage import ensure_playlist_folders


def ensure_playlists_from_folders(db: Session):
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
        for pl in db.query(Playlist).all():
            if pl.folder and pl.name not in (DEFAULT_PLAYLIST_NAME, LIKED_SONGS_NAME):
                if not (MUSIC_DIR / pl.folder).exists():
                    db.delete(pl)
        db.commit()
    except Exception as e:
        print(f"[ASH] ensure_playlists_from_folders error: {e}")


def sync_playlist_folder_tracks(db: Session):
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
        db.flush()
        try:
            cover_name = save_cover_for_track(track.id, f)
            if cover_name:
                track.cover_path = cover_name
                if album_obj and not getattr(album_obj, "cover_path", None):
                    album_cover = save_cover_for_album(album_obj.id, cover_name)
                    if album_cover:
                        album_obj.cover_path = album_cover
        except Exception as e:
            print(f"[ASH] scan cover error {rel}: {e}")
        added += 1
    try:
        missing = db.query(Track).filter((Track.cover_path == None) | (Track.cover_path == "")).all()
        for t in missing:
            p = Path(t.filepath)
            if not p.exists():
                p = MUSIC_DIR / t.filename
            if not p.exists():
                continue
            try:
                cover_name = save_cover_for_track(t.id, p)
                if cover_name:
                    t.cover_path = cover_name
                    if t.album_id:
                        alb = db.query(Album).filter(Album.id == t.album_id).first()
                        if alb is not None and not getattr(alb, "cover_path", None):
                            album_cover = save_cover_for_album(alb.id, cover_name)
                            if album_cover:
                                alb.cover_path = album_cover
            except Exception as e:
                print(f"[ASH] backfill cover error {t.filename}: {e}")
        for alb in db.query(Album).filter((Album.cover_path == None) | (Album.cover_path == "")).all():
            try:
                first = db.query(Track).filter(Track.album_id == alb.id, Track.cover_path.isnot(None)).first()
                if first and first.cover_path:
                    album_cover = save_cover_for_album(alb.id, first.cover_path)
                    if album_cover:
                        alb.cover_path = album_cover
            except Exception:
                pass
        db.commit()
    except Exception as e:
        print(f"[ASH] backfill covers error: {e}")
    for t in db.query(Track).all():
        exists = Path(t.filepath).exists() or (MUSIC_DIR / t.filename).exists()
        if not Path(t.filepath).exists() and (MUSIC_DIR / t.filename).exists():
            t.filepath = str(MUSIC_DIR / t.filename)
        if not exists:
            db.delete(t)
    db.commit()
    empty = db.query(Album).filter(~Album.tracks.any()).all()
    if empty:
        for alb in empty:
            db.delete(alb)
        db.commit()
    try:
        from ..config import COVERS_DIR as _CD

        if _CD.exists():
            used = {t.cover_path for t in db.query(Track.cover_path).all() if t[0]}
            used |= {f"album_{a.id}{Path(a.cover_path).suffix}" if a.cover_path else "" for a in db.query(Album).all()}
            used_album = {a.cover_path for a in db.query(Album).all() if a.cover_path}
            used |= used_album
            for f in _CD.iterdir():
                if f.is_file() and f.name not in used:
                    try:
                        f.unlink()
                    except Exception:
                        pass
    except Exception as e:
        print(f"[ASH] covers cleanup error: {e}")
    ensure_playlists_from_folders(db)
    sync_playlist_folder_tracks(db)
    return added

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request, Query, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..config import MUSIC_DIR, SUPPORTED_EXTENSIONS, MAX_UPLOAD_SIZE, LIKED_SONGS_NAME
from ..database import get_db
from ..models import Track, Playlist, Album
from ..schemas import TrackResponse
from ..services.albums import get_or_create_album
from ..services.metadata import extract_metadata
from ..services.search import normalize_text, token_matches
from ..services.storage import file_iterator, get_playlist_folder

router = APIRouter(tags=["tracks"])


@router.get("/api/tracks", response_model=List[TrackResponse])
def list_tracks(
    search: Optional[str] = Query(None, description="Поиск по названию/артисту/альбому"),
    artist: Optional[str] = None,
    album: Optional[str] = None,
    genre: Optional[str] = None,
    album_id: Optional[int] = None,
    sort: str = "created_at",
    order: str = "desc",
    db: Session = Depends(get_db),
):
    q = db.query(Track)
    if artist:
        q = q.filter(Track.artist == artist)
    if album:
        q = q.filter(Track.album == album)
    if album_id:
        q = q.filter(Track.album_id == album_id)
    if genre:
        q = q.filter(Track.genre == genre)

    allowed_sort = {"created_at": Track.created_at, "title": Track.title, "artist": Track.artist, "album": Track.album, "duration": Track.duration, "year": Track.year}
    allowed_order = {"asc", "desc"}
    col = allowed_sort.get(sort, Track.created_at)
    if order not in allowed_order:
        order = "desc"
    if order == "asc":
        q = q.order_by(col.asc())
    else:
        q = q.order_by(col.desc())

    tracks = q.all()

    if search and search.strip():
        norm_tokens = normalize_text(search).split()
        if norm_tokens:
            def haystack(t: Track) -> str:
                return normalize_text(f"{t.title} {t.artist} {t.album} {t.genre or ''}")

            def matches(t: Track) -> bool:
                hay = haystack(t)
                return all(token_matches(tok, hay) for tok in norm_tokens)

            orig_index = {t.id: i for i, t in enumerate(tracks)}
            tracks = [t for t in tracks if matches(t)]

            def rank(t: Track):
                hay = haystack(t)
                exact = sum(1 for tok in norm_tokens if tok in hay)
                return (-exact, orig_index.get(t.id, 0))

            tracks.sort(key=rank)

    return tracks


@router.get("/api/tracks/{track_id}", response_model=TrackResponse)
def get_track(track_id: int, db: Session = Depends(get_db)):
    t = db.query(Track).filter(Track.id == track_id).first()
    if not t:
        raise HTTPException(404, "Трек не найден")
    return t


@router.delete("/api/tracks/{track_id}")
def delete_track(track_id: int, db: Session = Depends(get_db)):
    t = db.query(Track).filter(Track.id == track_id).first()
    if not t:
        raise HTTPException(404, "Трек не найден")
    album_id = t.album_id
    try:
        p = Path(t.filepath)
        if not p.exists():
            p = MUSIC_DIR / t.filename
        p.unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(t)
    db.commit()
    if album_id:
        alb = db.query(Album).filter(Album.id == album_id).first()
        if alb and not alb.tracks:
            db.delete(alb)
            db.commit()
    return {"ok": True}


@router.get("/api/stream/{track_id}")
def stream_track(track_id: int, request: Request, db: Session = Depends(get_db)):
    import mimetypes

    t = db.query(Track).filter(Track.id == track_id).first()
    if not t:
        raise HTTPException(404, "Трек не найден")
    path = Path(t.filepath)
    if not path.exists():
        path = MUSIC_DIR / t.filename
    if not path.exists():
        raise HTTPException(404, "Файл не найден на диске")
    if str(path) != t.filepath:
        t.filepath = str(path)
        try:
            db.commit()
        except Exception:
            pass
    t.play_count = (t.play_count or 0) + 1
    db.commit()
    file_size = path.stat().st_size
    content_type = mimetypes.guess_type(str(path))[0] or "audio/mpeg"
    range_header = request.headers.get("range")
    if range_header:
        try:
            _, range_val = range_header.split("=")
            start_s, end_s = range_val.split("-")
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else file_size - 1
        except Exception:
            start, end = 0, file_size - 1
        if end >= file_size:
            end = file_size - 1
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
            "Content-Type": content_type,
        }
        return StreamingResponse(file_iterator(path, start, end), status_code=206, headers=headers)
    headers = {"Accept-Ranges": "bytes", "Content-Length": str(file_size)}
    return StreamingResponse(file_iterator(path), media_type=content_type, headers=headers)


@router.post("/api/upload", response_model=List[TrackResponse])
def upload_tracks(files: List[UploadFile] = File(...), playlist_id: Optional[int] = Form(None), db: Session = Depends(get_db)):
    if len(files) > 50:
        raise HTTPException(400, "Слишком много файлов за раз (макс 50)")
    created = []
    target_folder = MUSIC_DIR
    target_playlist = None
    if playlist_id is not None:
        target_playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
        if target_playlist:
            if target_playlist.name == LIKED_SONGS_NAME:
                target_folder = MUSIC_DIR
            else:
                target_folder = get_playlist_folder(target_playlist, ensure_exists=True)
    for upload in files:
        if not upload.filename:
            continue
        if getattr(upload, "size", None) is not None and upload.size is not None and upload.size > MAX_UPLOAD_SIZE:
            raise HTTPException(413, f"Файл {upload.filename} превышает лимит {MAX_UPLOAD_SIZE // (1024*1024)} MB")
        ext = Path(upload.filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue
        safe_name = Path(upload.filename).name
        orig_stem = Path(safe_name).stem
        orig_suffix = Path(safe_name).suffix
        dest = target_folder / safe_name
        counter = 1
        while dest.exists():
            dest = target_folder / f"{orig_stem}_{counter}{orig_suffix}"
            counter += 1
        written = 0
        with open(dest, "wb") as out:
            while True:
                chunk = upload.file.read(8192)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_SIZE:
                    out.close()
                    try:
                        dest.unlink(missing_ok=True)
                    except Exception:
                        pass
                    raise HTTPException(413, f"Файл {upload.filename} превышает лимит {MAX_UPLOAD_SIZE // (1024*1024)} MB")
                out.write(chunk)
        try:
            if dest.stat().st_size > MAX_UPLOAD_SIZE:
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"Файл {upload.filename} превышает лимит")
        except HTTPException:
            raise
        except Exception:
            pass
        meta = extract_metadata(dest)
        album_obj = get_or_create_album(db, meta.get("album", "Unknown Album"), meta.get("artist", "Unknown Artist"), meta.get("year"), meta.get("genre"))
        track = Track(
            title=meta.get("title", dest.stem),
            artist=meta.get("artist", "Unknown Artist"),
            album=meta.get("album", "Unknown Album"),
            album_id=album_obj.id if album_obj else None,
            duration=meta.get("duration", 0.0),
            filename=str(dest.relative_to(MUSIC_DIR)),
            filepath=str(dest),
            file_size=dest.stat().st_size,
            bitrate=meta.get("bitrate"),
            year=meta.get("year"),
            genre=meta.get("genre"),
        )
        db.add(track)
        db.commit()
        db.refresh(track)
        created.append(track)

    if target_playlist and created:
        for t in created:
            if t not in target_playlist.tracks:
                target_playlist.tracks.append(t)
        db.commit()

    return created


@router.get("/api/artists")
def list_artists(db: Session = Depends(get_db)):
    rows = db.query(Track.artist).distinct().all()
    return sorted([r[0] for r in rows if r[0]])

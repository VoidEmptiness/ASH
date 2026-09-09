import shutil
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from ..config import MUSIC_DIR, LIKED_SONGS_NAME
from ..database import get_db
from ..models import Track, Playlist, Album
from ..schemas import PlaylistCreate, PlaylistResponse, PlaylistUpdate
from ..services.library import ensure_playlists_from_folders, sync_playlist_folder_tracks
from ..services.metadata import safe_folder_name
from ..services.serializers import serialize_track
from ..services.storage import get_playlist_folder

router = APIRouter(tags=["playlists"])


def playlist_to_response(pl: Playlist):
    return {
        "id": pl.id,
        "name": pl.name,
        "description": pl.description,
        "cover_color": pl.cover_color,
        "folder": pl.folder,
        "created_at": pl.created_at,
        "tracks": [serialize_track(t) for t in pl.tracks],
        "track_count": len(pl.tracks),
    }


@router.get("/api/playlists", response_model=List[PlaylistResponse])
def list_playlists(db: Session = Depends(get_db)):
    ensure_playlists_from_folders(db)
    sync_playlist_folder_tracks(db)
    pls = db.query(Playlist).options(joinedload(Playlist.tracks)).all()
    return [playlist_to_response(p) for p in pls]


@router.post("/api/playlists", response_model=PlaylistResponse)
def create_playlist(data: PlaylistCreate, db: Session = Depends(get_db)):
    if db.query(Playlist).filter(Playlist.name == data.name).first():
        raise HTTPException(400, "Плейлист с таким именем уже существует")
    pl = Playlist(name=data.name, description=data.description or "", cover_color=data.cover_color or "#2a2a2a")
    base = safe_folder_name(data.name)
    candidate = base
    counter = 1
    existing = {p.folder for p in db.query(Playlist).all() if p.folder}
    while candidate in existing:
        counter += 1
        candidate = f"{base}_{counter}"
    pl.folder = candidate
    db.add(pl)
    db.commit()
    db.refresh(pl)
    try:
        (MUSIC_DIR / candidate).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[ASH] playlist folder error {e}")
    return playlist_to_response(pl)


@router.get("/api/playlists/{pid}", response_model=PlaylistResponse)
def get_playlist(pid: int, db: Session = Depends(get_db)):
    pl = db.query(Playlist).filter(Playlist.id == pid).first()
    if not pl:
        raise HTTPException(404, "Плейлист не найден")
    return playlist_to_response(pl)


@router.patch("/api/playlists/{pid}", response_model=PlaylistResponse)
def update_playlist(pid: int, data: PlaylistUpdate, db: Session = Depends(get_db)):
    pl = db.query(Playlist).filter(Playlist.id == pid).first()
    if not pl:
        raise HTTPException(404, "Плейлист не найден")
    old_folder = pl.folder
    if data.name is not None and data.name != pl.name:
        new_folder = safe_folder_name(data.name)
        if new_folder != old_folder:
            existing = {p.folder for p in db.query(Playlist).filter(Playlist.id != pid).all() if p.folder}
            candidate = new_folder
            counter = 1
            while candidate in existing:
                counter += 1
                candidate = f"{new_folder}_{counter}"
            try:
                old_path = MUSIC_DIR / old_folder if old_folder else None
                new_path = MUSIC_DIR / candidate
                if old_path and old_path.exists():
                    old_path.rename(new_path)
                    for t in pl.tracks:
                        if old_folder and t.filename.startswith(old_folder + "/"):
                            new_filename = t.filename.replace(old_folder + "/", candidate + "/", 1)
                            t.filename = new_filename
                            t.filepath = str(MUSIC_DIR / new_filename)
                else:
                    new_path.mkdir(parents=True, exist_ok=True)
                pl.folder = candidate
            except Exception as e:
                print(f"[ASH] rename folder error {e}")
        pl.name = data.name
    if data.description is not None:
        pl.description = data.description
    if data.cover_color is not None:
        pl.cover_color = data.cover_color
    db.commit()
    db.refresh(pl)
    return playlist_to_response(pl)


@router.delete("/api/playlists/{pid}")
def delete_playlist(pid: int, db: Session = Depends(get_db)):
    pl = db.query(Playlist).filter(Playlist.id == pid).first()
    if not pl:
        raise HTTPException(404, "Плейлист не найден")
    if pl.name == LIKED_SONGS_NAME:
        raise HTTPException(403, "Плейлист Liked Songs нельзя удалить")
    folder_name = pl.folder
    folder_to_delete = MUSIC_DIR / folder_name if folder_name else None
    db.delete(pl)
    db.commit()
    if folder_to_delete and folder_to_delete.exists():
        try:
            shutil.rmtree(folder_to_delete)
        except Exception as e:
            print(f"[ASH] delete playlist folder error {e}")
        if folder_name:
            try:
                prefix = folder_name + "/"
                tracks_to_del = db.query(Track).filter(Track.filename.startswith(prefix)).all()
                for t in tracks_to_del:
                    db.delete(t)
                empty = db.query(Album).filter(~Album.tracks.any()).all()
                for alb in empty:
                    db.delete(alb)
                db.commit()
            except Exception as e:
                print(f"[ASH] delete playlist tracks error {e}")
    return {"ok": True}


@router.post("/api/playlists/{pid}/tracks/{tid}")
def add_to_playlist(pid: int, tid: int, db: Session = Depends(get_db)):
    pl = db.query(Playlist).filter(Playlist.id == pid).first()
    if not pl:
        raise HTTPException(404, "Плейлист не найден")
    tr = db.query(Track).filter(Track.id == tid).first()
    if not tr:
        raise HTTPException(404, "Трек не найден")
    if tr not in pl.tracks:
        pl.tracks.append(tr)
        db.commit()
    return {"ok": True}


@router.delete("/api/playlists/{pid}/tracks/{tid}")
def remove_from_playlist(pid: int, tid: int, db: Session = Depends(get_db)):
    pl = db.query(Playlist).filter(Playlist.id == pid).first()
    if not pl:
        raise HTTPException(404, "Плейлист не найден")
    tr = db.query(Track).filter(Track.id == tid).first()
    if not tr:
        raise HTTPException(404, "Трек не найден")
    if tr in pl.tracks:
        pl.tracks.remove(tr)
        db.commit()
    return {"ok": True}

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Track, Playlist, Album
from ..services.library import scan_music_folder

router = APIRouter(tags=["stats"])


@router.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    total_tracks = db.query(func.count(Track.id)).scalar() or 0
    total_playlists = db.query(func.count(Playlist.id)).scalar() or 0
    total_albums = db.query(func.count(Album.id)).scalar() or 0
    total_duration = db.query(func.coalesce(func.sum(Track.duration), 0)).scalar() or 0
    total_size = db.query(func.coalesce(func.sum(Track.file_size), 0)).scalar() or 0
    return {
        "tracks": total_tracks,
        "playlists": total_playlists,
        "albums": total_albums,
        "duration": float(total_duration),
        "size": int(total_size),
    }


@router.post("/api/scan")
def scan(db: Session = Depends(get_db)):
    added = scan_music_folder(db)
    return {"added": added, "message": f"Добавлено {added} треков"}

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Track, Album
from ..schemas import AlbumResponse

router = APIRouter(tags=["albums"])


@router.get("/api/albums", response_model=List[AlbumResponse])
def list_albums(db: Session = Depends(get_db)):
    empty = db.query(Album).filter(~Album.tracks.any()).all()
    if empty:
        for alb in empty:
            db.delete(alb)
        db.commit()
    albums = db.query(Album).options(joinedload(Album.tracks)).order_by(Album.title.asc()).all()
    if not albums:
        rows = db.query(Track.album).distinct().all()
        filtered = [r for r in rows if r[0] and db.query(func.count(Track.id)).filter(Track.album == r[0]).scalar() > 0]
        return [{"id": 0, "title": r[0], "artist": "Various", "track_count": db.query(func.count(Track.id)).filter(Track.album == r[0]).scalar(), "tracks": []} for r in filtered]
    result = []
    for alb in albums:
        result.append({
            "id": alb.id,
            "title": alb.title,
            "artist": alb.artist,
            "year": alb.year,
            "genre": alb.genre,
            "cover_color": alb.cover_color,
            "created_at": alb.created_at,
            "track_count": len(alb.tracks),
            "tracks": alb.tracks,
        })
    return result


@router.get("/api/albums/{album_id}", response_model=AlbumResponse)
def get_album(album_id: int, db: Session = Depends(get_db)):
    alb = db.query(Album).options(joinedload(Album.tracks)).filter(Album.id == album_id).first()
    if not alb:
        raise HTTPException(404, "Альбом не найден")
    return {
        "id": alb.id,
        "title": alb.title,
        "artist": alb.artist,
        "year": alb.year,
        "genre": alb.genre,
        "cover_color": alb.cover_color,
        "created_at": alb.created_at,
        "track_count": len(alb.tracks),
        "tracks": alb.tracks,
    }

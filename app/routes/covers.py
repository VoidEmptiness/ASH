"""Отдача обложек треков и альбомов."""
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from ..config import COVERS_DIR
from ..database import get_db
from ..models import Track, Album
from ..services.covers import cover_file_response_path, placeholder_svg

router = APIRouter(tags=["covers"])


def _file_response(path: Path):
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    return FileResponse(
        str(path),
        media_type=mime,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/api/covers/{track_id}")
def get_track_cover(
    track_id: int,
    placeholder: bool = Query(False, description="Вернуть SVG-заглушку если обложки нет"),
    db: Session = Depends(get_db),
):
    t = db.query(Track).filter(Track.id == track_id).first()
    if not t:
        raise HTTPException(404, "Трек не найден")
    p = cover_file_response_path(getattr(t, "cover_path", None))
    if p:
        return _file_response(p)
    if placeholder:
        letter = (t.title or "?")[:1]
        return Response(
            content=placeholder_svg(letter),
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    raise HTTPException(404, "Обложка не найдена")


@router.get("/api/albums/{album_id}/cover")
def get_album_cover(
    album_id: int,
    placeholder: bool = Query(False),
    db: Session = Depends(get_db),
):
    alb = db.query(Album).filter(Album.id == album_id).first()
    if not alb:
        raise HTTPException(404, "Альбом не найден")
    p = cover_file_response_path(getattr(alb, "cover_path", None))
    if p:
        return _file_response(p)
    # fallback: первая обложка трека альбома
    first = (
        db.query(Track)
        .filter(Track.album_id == album_id, Track.cover_path.isnot(None))
        .first()
    )
    if first:
        fp = cover_file_response_path(first.cover_path)
        if fp:
            return _file_response(fp)
    if placeholder:
        return Response(
            content=placeholder_svg((alb.title or "?")[:1]),
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    raise HTTPException(404, "Обложка не найдена")

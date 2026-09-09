"""Точка входа FastAPI — только wiring (как в Video-Library/app/main.py).

Вся бизнес-логика живёт в app/services/*, HTTP-слой — в app/routes/*.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import LIKED_SONGS_NAME, DEFAULT_PLAYLIST_NAME
from .database import SessionLocal
from .models import Track, Playlist
from .services.albums import get_or_create_album
from .services.library import scan_music_folder
from .services.migrations import init_db
from .services.storage import ensure_playlist_folders, get_playlist_folder


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup — инициализация БД и фонотеки
    init_db()
    db = SessionLocal()
    try:
        scan_music_folder(db)
        # ensure default playlists
        if not db.query(Playlist).filter(Playlist.name == DEFAULT_PLAYLIST_NAME).first():
            p = Playlist(name=DEFAULT_PLAYLIST_NAME, description="Автоматический плейлист — всё из библиотеки", cover_color="#3a3a3a")
            db.add(p)
            db.commit()
            db.refresh(p)
            get_playlist_folder(p, ensure_exists=True)
            ensure_playlist_folders(db)
        else:
            ensure_playlist_folders(db)
        # Liked Songs — всегда существует, без папки на диске, неудаляемый
        if not db.query(Playlist).filter(Playlist.name == LIKED_SONGS_NAME).first():
            liked = Playlist(name=LIKED_SONGS_NAME, description="Понравившиеся треки", cover_color="#d6d3cf", folder=None)
            db.add(liked)
            db.commit()
        else:
            # миграция: перекрашиваем Liked Songs из красного в пепельный
            liked = db.query(Playlist).filter(Playlist.name == LIKED_SONGS_NAME).first()
            if liked and liked.cover_color == "#e63946":
                liked.cover_color = "#d6d3cf"
                db.commit()
        for t in db.query(Track).filter(Track.album_id == None).all():  # noqa: E711
            if t.album and t.album != "Unknown Album":
                alb = get_or_create_album(db, t.album, t.artist, t.year, t.genre)
                if alb:
                    t.album_id = alb.id
        db.commit()
    finally:
        db.close()
    yield


app = FastAPI(
    title="ASH — Auralis Self Hosted",
    description="Пепельный минимализм. Твоя музыка — твой пепел.",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "static")),
    name="static",
)

# Роуты — как в Video-Library: каждый домен в своём модуле
from .routes.pages import router as pages_router  # noqa: E402
from .routes.stats import router as stats_router  # noqa: E402
from .routes.tracks import router as tracks_router  # noqa: E402
from .routes.albums import router as albums_router  # noqa: E402
from .routes.playlists import router as playlists_router  # noqa: E402

app.include_router(pages_router)
app.include_router(stats_router)
app.include_router(tracks_router)
app.include_router(albums_router)
app.include_router(playlists_router)

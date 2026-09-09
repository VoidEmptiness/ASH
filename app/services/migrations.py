"""Миграции схемы без alembic (аналог services/migrations.py в Video-Library)."""
from sqlalchemy import inspect, text

from ..database import Base, engine


def ensure_schema():
    """Добавляет недостающие колонки/таблицы если их нет."""
    try:
        inspector = inspect(engine)
        if inspector.has_table("playlists"):
            cols = [c["name"] for c in inspector.get_columns("playlists")]
            if "folder" not in cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE playlists ADD COLUMN folder VARCHAR"))
                print("[ASH] migrated playlists.folder")
        if inspector.has_table("tracks"):
            cols = [c["name"] for c in inspector.get_columns("tracks")]
            if "album_id" not in cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE tracks ADD COLUMN album_id INTEGER REFERENCES albums(id)"))
                print("[ASH] migrated tracks.album_id")
            if "cover_path" not in cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE tracks ADD COLUMN cover_path VARCHAR"))
                print("[ASH] migrated tracks.cover_path")
        if inspector.has_table("albums"):
            cols = [c["name"] for c in inspector.get_columns("albums")]
            if "cover_path" not in cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE albums ADD COLUMN cover_path VARCHAR"))
                print("[ASH] migrated albums.cover_path")
    except Exception as e:
        print(f"[ASH] ensure_schema error: {e}")


def init_db():
    ensure_schema()
    Base.metadata.create_all(bind=engine)

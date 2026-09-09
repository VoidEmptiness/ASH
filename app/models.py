from sqlalchemy import Column, Integer, String, Float, DateTime, Table, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

playlist_tracks = Table(
    "playlist_tracks",
    Base.metadata,
    Column("playlist_id", Integer, ForeignKey("playlists.id", ondelete="CASCADE")),
    Column("track_id", Integer, ForeignKey("tracks.id", ondelete="CASCADE")),
)

class Album(Base):
    __tablename__ = "albums"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    artist = Column(String, default="Unknown Artist", index=True)
    year = Column(String, nullable=True)
    genre = Column(String, nullable=True)
    cover_color = Column(String, default="#2a2a2a")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tracks = relationship("Track", back_populates="album_obj")


class Track(Base):
    __tablename__ = "tracks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    artist = Column(String, default="Unknown Artist", index=True)
    album = Column(String, default="Unknown Album", index=True)  # legacy string for compatibility
    album_id = Column(Integer, ForeignKey("albums.id", ondelete="SET NULL"), nullable=True, index=True)
    duration = Column(Float, default=0.0)  # seconds
    filename = Column(String, nullable=False, unique=True)
    filepath = Column(String, nullable=False)
    cover_path = Column(String, nullable=True)
    file_size = Column(Integer, default=0)
    bitrate = Column(Integer, nullable=True)
    year = Column(String, nullable=True)
    genre = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    play_count = Column(Integer, default=0)

    playlists = relationship("Playlist", secondary=playlist_tracks, back_populates="tracks")
    album_obj = relationship("Album", back_populates="tracks")


class Playlist(Base):
    __tablename__ = "playlists"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    cover_color = Column(String, default="#2a2a2a")
    folder = Column(String, nullable=True)  # относительная папка в MUSIC_DIR, например "My Playlist"

    tracks = relationship("Track", secondary=playlist_tracks, back_populates="playlists")

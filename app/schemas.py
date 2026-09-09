from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class TrackBase(BaseModel):
    title: str
    artist: str
    album: str
    duration: float
    filename: str
    year: Optional[str] = None
    genre: Optional[str] = None

class TrackResponse(TrackBase):
    id: int
    file_size: int
    play_count: int
    created_at: Optional[datetime] = None
    bitrate: Optional[int] = None
    album_id: Optional[int] = None

    class Config:
        from_attributes = True

class AlbumResponse(BaseModel):
    id: int
    title: str
    artist: str
    year: Optional[str] = None
    genre: Optional[str] = None
    cover_color: str
    created_at: Optional[datetime] = None
    track_count: int = 0
    tracks: List[TrackResponse] = []

    class Config:
        from_attributes = True

class PlaylistCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    cover_color: Optional[str] = "#2a2a2a"

class PlaylistResponse(BaseModel):
    id: int
    name: str
    description: str
    cover_color: str
    folder: Optional[str] = None
    created_at: Optional[datetime] = None
    tracks: List[TrackResponse] = []
    track_count: int = 0

    class Config:
        from_attributes = True

class PlaylistUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    cover_color: Optional[str] = None

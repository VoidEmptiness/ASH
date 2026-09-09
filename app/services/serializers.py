from ..models import Track, Album


def track_cover_url(t: Track) -> str | None:
    if getattr(t, "cover_path", None):
        return f"/api/covers/{t.id}"
    return None


def serialize_track(t: Track) -> dict:
    url = track_cover_url(t)
    return {
        "id": t.id,
        "title": t.title,
        "artist": t.artist,
        "album": t.album,
        "duration": t.duration or 0.0,
        "filename": t.filename,
        "year": t.year,
        "genre": t.genre,
        "file_size": t.file_size or 0,
        "play_count": t.play_count or 0,
        "created_at": t.created_at,
        "bitrate": t.bitrate,
        "album_id": t.album_id,
        "cover_url": url,
        "has_cover": bool(url),
    }


def album_cover_url(a: Album) -> str | None:
    if getattr(a, "cover_path", None):
        return f"/api/albums/{a.id}/cover"
    try:
        tracks = list(getattr(a, "tracks", []) or [])
        for t in tracks:
            if getattr(t, "cover_path", None):
                return f"/api/covers/{t.id}"
    except Exception:
        pass
    return None


def serialize_album(a: Album) -> dict:
    tracks = list(getattr(a, "tracks", []) or [])
    url = album_cover_url(a)
    return {
        "id": a.id,
        "title": a.title,
        "artist": a.artist,
        "year": a.year,
        "genre": a.genre,
        "cover_color": a.cover_color or "#2a2a2a",
        "cover_url": url,
        "has_cover": bool(url),
        "created_at": a.created_at,
        "track_count": len(tracks),
        "tracks": [serialize_track(t) for t in tracks],
    }

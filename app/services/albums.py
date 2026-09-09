from ..models import Album


def get_or_create_album(db, title: str, artist: str = "Unknown Artist", year=None, genre=None):
    if not title or title == "Unknown Album":
        return None
    album = db.query(Album).filter(Album.title == title, Album.artist == (artist or "Unknown Artist")).first()
    if album:
        return album
    album = Album(title=title, artist=artist or "Unknown Artist", year=year, genre=genre)
    db.add(album)
    db.flush()
    return album

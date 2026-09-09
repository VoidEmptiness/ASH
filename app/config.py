import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MUSIC_DIR = Path(os.getenv("MUSIC_DIR", BASE_DIR / "music"))
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'ash.db'}")
COVERS_DIR = Path(os.getenv("COVERS_DIR", DATA_DIR / "covers"))

MUSIC_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
COVERS_DIR.mkdir(parents=True, exist_ok=True)

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".opus", ".wma"}
MAX_UPLOAD_SIZE = 500 * 1024 * 1024

LIKED_SONGS_NAME = "Liked Songs"
DEFAULT_PLAYLIST_NAME = "Из пепла"

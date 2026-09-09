# ASH — Auralis Self Hosted

**Пепельный минимализм. Твоя музыка — твой пепел.**

Self-hosted сервис для прослушивания музыки. Тёмная тема в угольно-серых / пепельных тонах, минималистичный интерфейс, запуск в один `docker compose`.

![ASH](https://img.shields.io/badge/style-ash%20minimalism-2a2a2a) ![Python](https://img.shields.io/badge/python-3.11-9a9997) ![FastAPI](https://img.shields.io/badge/FastAPI-0.110-d6d3cf)

---

## Философия

> *“Из пепла рождается тишина. Из тишины — звук.”*

`ash` — пепел. Интерфейс — как остывший уголь: матовый, зернистый, без глянца. Никаких неоновых акцентов, только оттенки пепла: `#0a0a0b` → `#e9e7e3`. Моноширинный шрифт, сетка, воздух. Ничего лишнего — только звук.

## Стек

- **Backend:** Python 3.11 + FastAPI + SQLAlchemy (SQLite) + Mutagen + Jinja2
- **Frontend:** Vanilla HTML/CSS/JS (без сборки), Inter + JetBrains Mono
- **Infra:** Docker + Docker Compose

## Структура
```
ASH/
├── app/
│   ├── main.py              # FastAPI приложение, lifespan и подключение роутеров
│   ├── config.py            # Пути, лимиты, имена системных плейлистов
│   ├── models.py            # SQLAlchemy ORM: Track, Playlist, Album
│   ├── schemas.py           # Pydantic-схемы API
│   ├── database.py          # Engine, SessionLocal, Base, get_db
│   ├── routes/              # HTTP-слой (APIRouter по доменам)
│   │   ├── pages.py         # GET / — HTML страница
│   │   ├── stats.py         # /api/stats, /api/scan
│   │   ├── tracks.py        # /api/tracks, /api/stream, /api/upload, /api/artists
│   │   ├── albums.py        # /api/albums
│   │   └── playlists.py     # /api/playlists
│   ├── services/            # Бизнес-логика
│   │   ├── library.py       # scan_music_folder, sync плейлистов с папками
│   │   ├── storage.py       # Папки плейлистов, file_iterator, пути
│   │   ├── metadata.py      # Mutagen: extract_metadata, safe_folder_name
│   │   ├── search.py        # normalize_text, token_matches
│   │   ├── albums.py        # get_or_create_album
│   │   └── migrations.py    # ensure_schema / init_db без alembic
│   ├── templates/index.html
│   └── static/css/style.css
│   └── static/js/app.js
├── music/               # <- сюда кидай музыку
├── data/                # SQLite база ash.db
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Быстрый старт

### Docker (рекомендуется)

```bash
git clone https://github.com/VoidEmptiness/ASH.git && cd ASH && docker compose up -d --build
```

> Порт `8000` можно поменять в `docker-compose.yml`.
> Папки `music` и `data` монтируются как volumes

## API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/tracks?search=&sort=&order=` | Список треков |
| GET | `/api/tracks/{id}` | Один трек |
| GET | `/api/stream/{id}` | Стрим аудио (Range) |
| POST | `/api/upload` | Загрузка файлов (multipart `files`) |
| DELETE | `/api/tracks/{id}` | Удалить трек + файл |
| POST | `/api/scan` | Пересканировать `music/` |
| GET | `/api/stats` | Статистика |
| GET | `/api/artists` | Список артистов |
| GET | `/api/albums` | Список альбомов |
| GET/POST | `/api/playlists` | Плейлисты |
| POST/DELETE | `/api/playlists/{pid}/tracks/{tid}` | Управление треками в плейлисте |

## Кастомизация темы

Цвета в `:root` — `app/static/css/style.css:1`:
```css
--bg:#0a0a0b;
--surface:#1a1a1c;
--ash-light:#d6d3cf;
--text:#e9e7e3;
```
Поменяй и пересобери контейнер.

## TODO / Идеи

- [ ] Синхронизация офлайн музыки между устройствами
- [ ] Обложки к трекам.
- [ ] Поддержка клипов, просмотр клипов.


---

**ASH** — *Auralis Self Hosted.*

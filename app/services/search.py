"""Нормализация текста и нечёткий поиск (бывший блок search из utils.py)."""
import re
import unicodedata
import difflib

_NORMALIZE_MAP = str.maketrans({
    "ё": "е",
    "Ё": "е",
})


def normalize_text(text: str) -> str:
    """Нормализует текст для поиска: нижний регистр, ё→е, NFKD, удаление лишних символов."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().translate(_NORMALIZE_MAP)
    text = re.sub(r"[^a-zа-я0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def token_matches(token: str, haystack: str) -> bool:
    """Проверяет токен в haystack: точное вхождение или нечёткое (fuzzy) для опечаток."""
    if token in haystack:
        return True
    hay_nospace = haystack.replace(" ", "")
    if token in hay_nospace:
        return True
    if token.replace(" ", "") in hay_nospace:
        return True
    for word in haystack.split():
        if abs(len(word) - len(token)) > 2:
            continue
        if len(word) < 3 or len(token) < 3:
            continue
        if difflib.SequenceMatcher(None, token, word).ratio() >= 0.82:
            return True
    if len(token) >= 4:
        for i in range(len(hay_nospace) - len(token) + 1):
            window = hay_nospace[i:i + len(token) + 1]
            if difflib.SequenceMatcher(None, token, window).ratio() >= 0.85:
                return True
    return False


def matches_search(track, query: str) -> bool:
    hay = normalize_text(f"{track.title} {track.artist} {track.album} {track.genre or ''}")
    tokens = normalize_text(query).split()
    if not tokens:
        return True
    return all(token_matches(tok, hay) for tok in tokens)

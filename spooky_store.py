"""Manual Spooky cache without API_ID.
You forward events wall to your own bot, it remembers and shows to users.
Storage: spooky_last.txt next to this file.
"""
import os
import time
import logging

log = logging.getLogger("spooky_store")

BASE = os.path.dirname(os.path.abspath(__file__))
PATH_RAW = os.path.join(BASE, "spooky_last.txt")
PATH_TS = os.path.join(BASE, "spooky_last_ts.txt")


def save_spooky_raw(text: str) -> int:
    text = (text or "").strip()
    if not text or "Анархия" not in text:
        raise ValueError("в тексте нет 'Анархия' - это не стена ивентов")
    with open(PATH_RAW, "w", encoding="utf-8") as f:
        f.write(text)
    now = int(time.time())
    with open(PATH_TS, "w", encoding="utf-8") as f:
        f.write(str(now))
    return len(text)


def load_spooky_raw():
    if not os.path.exists(PATH_RAW):
        return "", 0
    try:
        with open(PATH_RAW, encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return "", 0
    age = 10 ** 9
    try:
        with open(PATH_TS, encoding="utf-8") as f:
            ts = int(f.read().strip() or 0)
            age = int(time.time()) - ts
    except Exception:
        pass
    return raw, age


def get_spooky_manual_text(period: str = "current") -> str:
    from spooky_provider import parse_spooky_text, build_spooky_text
    raw, age = load_spooky_raw()
    if not raw:
        return (
            "🎃 Spooky пока пустой.\n"
            "Перешли мне стену ивентов от бота-источника (сообщение со списком 'Анархия ...').\n"
            "Я запомню и буду показывать всем."
        )
    try:
        parsed = parse_spooky_text(raw)
    except Exception as e:
        return f"❌ Не разобрал кеш: {e}"
    if not parsed:
        return "❌ В кеше 0 анархий (формат поменялся?). Перешли свежую стену."
    return build_spooky_text(parsed, period=period, cache_age=age)

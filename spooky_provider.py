"""Spooky source via userbot (Telethon). No API - asking other Telegram bot.

ENV needed:
  API_ID          int, from https://my.telegram.org
  API_HASH        str, from https://my.telegram.org
  SESSION_STRING  str, StringSession of extra account (see gen_session.py)
  SPOOKY_BOT      str, target bot username, e.g. @SpookyEventsBot
  SPOOKY_CMD      str, default /events
  SPOOKY_CACHE_TTL int, default 40 sec

Flow: user presses Spooky button in main bot -> this module connects as
extra account, sends SPOOKY_CMD to SPOOKY_BOT, waits, reads reply, parses.
Result is cached globally so 50 users don't spam target bot.
"""
import asyncio
import html
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone

log = logging.getLogger("spooky")

API_ID = int(os.getenv("API_ID", "0") or 0)
API_HASH = os.getenv("API_HASH", "").strip()
SESSION_STRING = os.getenv("SESSION_STRING", os.getenv("SESSION", "")).strip()
SPOOKY_BOT = os.getenv("SPOOKY_BOT", "").strip()
SPOOKY_CMD = os.getenv("SPOOKY_CMD", "/events").strip() or "/events"
try:
    CACHE_TTL = int(os.getenv("SPOOKY_CACHE_TTL", "40") or 40)
except ValueError:
    CACHE_TTL = 40

_lock = threading.Lock()
_cache = {"ts": 0.0, "raw": "", "parsed": []}


def is_configured() -> bool:
    return bool(API_ID and API_HASH and SESSION_STRING and SPOOKY_BOT)


def _need_setup_msg() -> str:
    return (
        "🎃 Spooky-источник не настроен.\n"
        "Нужно в Env добавить: API_ID, API_HASH, SESSION_STRING, SPOOKY_BOT.\n"
        "SESSION_STRING сгенерируй локально через gen_session.py."
    )


# ---------- parsing ----------

_ANARCHY_RE = re.compile(r"Анархия\s+(\d+)\s*:", re.IGNORECASE)
_TIMER_RE = re.compile(r"До следующего ивента\s*:\s*(.+)", re.IGNORECASE)


def parse_spooky_text(raw: str) -> list:
    """Raw wall of text -> list of dicts {server, has_event, name, loot, status, place, timer}."""
    if not raw:
        return []
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    # find all anarchy blocks
    matches = list(_ANARCHY_RE.finditer(text))
    if not matches:
        return []
    out = []
    for i, m in enumerate(matches):
        server = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        if not block:
            continue
        # timer-only?
        tm = _TIMER_RE.search(block)
        # event lines: look for [1] markers (can be several per block, take all)
        event_marks = list(re.finditer(r"\[1\]\s*(.+)", block))
        if not event_marks and tm:
            out.append({
                "server": server,
                "has_event": False,
                "name": "",
                "loot": "",
                "status": "",
                "place": "",
                "timer": tm.group(1).strip(),
                "raw_block": block[:500],
            })
            continue
        if not event_marks:
            # unknown block, keep as timer-ish
            out.append({
                "server": server,
                "has_event": False,
                "name": "",
                "loot": "",
                "status": block[:200],
                "place": "",
                "timer": "",
                "raw_block": block[:500],
            })
            continue
        for em in event_marks:
            # name line may include emoji before [1], keep it
            line_start = block.rfind("\n", 0, em.start())
            full_line = block[line_start + 1:em.end()].strip() if line_start != -1 else block[:em.end()].strip()
            # cut same-line part after [1]
            name = em.group(1).strip()
            # next lines until next [1] or end of block
            nxt = event_marks[event_marks.index(em) + 1].start() if event_marks.index(em) + 1 < len(event_marks) else len(block)
            tail = block[em.end():nxt]
            loot = ""
            status = ""
            place = ""
            timer = ""
            ml = re.search(r"Уровень лута\s*:\s*(.+)", tail)
            if ml:
                loot = ml.group(1).strip().split("\n")[0].strip()
            ms = re.search(r"Статус\s*:\s*(.+)", tail)
            if ms:
                status = ms.group(1).strip().split("\n")[0].strip()
            mc = re.search(r"Координаты\s*:\s*(.+)", tail)
            if mc:
                place = mc.group(1).strip().split("\n")[0].strip()
                place_kind = "coords"
            else:
                mw = re.search(r"Локация\s*:\s*(.+)", tail)
                if mw:
                    place = mw.group(1).strip().split("\n")[0].strip()
                    place_kind = "warp"
                else:
                    place_kind = ""
            mt = _TIMER_RE.search(tail)
            if mt:
                timer = mt.group(1).strip()
            out.append({
                "server": server,
                "has_event": True,
                "name": name,
                "full_line": full_line,
                "loot": loot,
                "status": status,
                "place": place,
                "place_kind": place_kind,
                "timer": timer,
                "raw_block": block[:500],
            })
    return out


def _anarchy_key(e: dict) -> tuple:
    try:
        return (int(e.get("server", "0")), e.get("name", ""))
    except ValueError:
        return (10 ** 9, str(e.get("server")))


def build_spooky_text(parsed: list, period: str = "current", cache_age: int = 0) -> str:
    if period == "upcoming":
        rows = [e for e in parsed if not e.get("has_event")]
        title = "🎃 <b>Spooky — ближайшие</b>"
        empty = "😴 Нет таймеров до следующего. Загляни в 🎃 текущие."
    else:
        rows = [e for e in parsed if e.get("has_event")]
        title = "🎃 <b>Spooky-ивенты — текущие</b>"
        empty = "😴 Активных spooky-ивентов нет. Загляни в 🕐 ближайшие."
    if not rows:
        return empty
    rows = sorted(rows, key=_anarchy_key)
    lines = [f"{title} <i>(обновлено {cache_age}с назад)</i>:\n"]
    for e in rows:
        srv = html.escape(str(e.get("server", "?")))
        if not e.get("has_event"):
            t = html.escape(e.get("timer", "—"))
            lines.append(f"<code>{srv}</code> Анархия — ⏳ до следующего: {t}")
            continue
        name = html.escape(e.get("name", "?"))
        # full_line already has emoji, but name is enough + keep emoji if present
        full = html.escape(e.get("full_line", name))
        loot = html.escape(e.get("loot", ""))
        status = html.escape(e.get("status", ""))
        place = html.escape(e.get("place", ""))
        pk = e.get("place_kind", "")
        line = f"\n🖥 <code>{srv}</code> Анархия\n  • {full}"
        if loot:
            line += f"\n    🎁 лут: {loot}"
        if status:
            line += f"\n    📌 {status}"
        if place:
            if pk == "coords":
                line += f"\n    📍 <code>{place}</code>"
            else:
                line += f"\n    📍 <code>{place}</code>"
        lines.append(line)
    return "\n".join(lines)


# ---------- fetching via Telethon ----------

async def _fetch_raw_async() -> str:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    target = SPOOKY_BOT
    if not target.startswith("@"):
        target = "@" + target
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("SESSION_STRING не авторизован (нужен новый логин через gen_session.py)")
        entity = await client.get_entity(target)
        before = datetime.now(timezone.utc)
        # /start first (some bots require it), then main cmd
        try:
            await client.send_message(entity, "/start")
            await asyncio.sleep(1.5)
        except Exception:
            pass
        await client.send_message(entity, SPOOKY_CMD)
        # target bot answers with long wall, can be split -> wait
        await asyncio.sleep(8)
        msgs = await client.get_messages(entity, limit=10)
        fresh = []
        for m in reversed(msgs):  # chronological
            if m.out:
                continue
            if not m.text:
                continue
            if not m.date:
                continue
            md = m.date
            if md.tzinfo is None:
                md = md.replace(tzinfo=timezone.utc)
            if md < before:
                continue
            fresh.append(m.text)
        # filter only resembling events wall
        walls = [t for t in fresh if "Анархия" in t]
        if walls:
            return "\n\n".join(walls)
        # fallback: last incoming msg even without marker (for debug)
        incoming = [t for t in fresh if t]
        if incoming:
            return "\n\n".join(incoming)
        raise RuntimeError("целевой бот не ответил за 8с (проверь SPOOKY_BOT и что /events работает с этого аккаунта)")
    finally:
        await client.disconnect()


def fetch_spooky_raw_sync(timeout: int = 40) -> str:
    return asyncio.run(asyncio.wait_for(_fetch_raw_async(), timeout=timeout))


def get_spooky_parsed(force: bool = False) -> tuple:
    """Returns (parsed_list, cache_age_sec). Uses cache, fetches if stale."""
    if not is_configured():
        raise RuntimeError(_need_setup_msg())
    now = time.time()
    with _lock:
        if not force and _cache["parsed"] and now - _cache["ts"] < CACHE_TTL:
            return _cache["parsed"], int(now - _cache["ts"])
    # fetch outside? keep inside lock to avoid parallel spam
    with _lock:
        now2 = time.time()
        if not force and _cache["parsed"] and now2 - _cache["ts"] < CACHE_TTL:
            return _cache["parsed"], int(now2 - _cache["ts"])
        raw = fetch_spooky_raw_sync()
        parsed = parse_spooky_text(raw)
        if not parsed:
            raise RuntimeError("разобрал 0 анархий из ответа (бот поменял формат?). Сырой ответ сохранен в логе.")
        _cache.update(ts=time.time(), raw=raw, parsed=parsed)
        return parsed, 0


def get_spooky_text(period: str = "current", force: bool = False) -> str:
    if not is_configured():
        return _need_setup_msg()
    try:
        parsed, age = get_spooky_parsed(force=force)
    except Exception as e:
        log.exception("spooky fetch failed")
        return f"❌ Ошибка Spooky: {html.escape(str(e))}"
    return build_spooky_text(parsed, period=period, cache_age=age)

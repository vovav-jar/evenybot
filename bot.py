"""ТГ-бот ивентов FunTime (funtime.me API). Python + telebot."""
import os
import re
import time
import logging
from collections import defaultdict

import requests
import telebot
from telebot import types
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(",", " ").split() if x.strip().isdigit()}
API_URL = "https://funtime.me/api/backend/api/v1/events?event-type=all&server-type="

# Каналы для обязательной подписки
CHANNELS = [
    {"label": "Leaf Client", "url": "https://t.me/leafclient", "chat_id": "@leafclient"},
    {"label": "Хата Котокрола", "url": "https://t.me/hatakotokrola", "chat_id": "@hatakotokrola"},
]
SUB_GATE_TEXT = "Для использования подпишитесь на каналы"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://funtime.me/events",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}

# id из API -> человеческое название
EVENT_NAMES = {
    # пользовательские
    "airdrop": "📦 Аирдроп",
    "myst_beacon": "🔮 Мистический маяк",
    "altarundead": "💀 Алтарь нежити",
    # системные
    "beacon": "🗼 Маяк",
    "geyser": "🌊 Гейзер",
    "vulkan": "🌋 Вулкан",
    "volcano": "🌋 Вулкан",
    "meteor_rain": "☄️ Метеоритный дождь",
    "meteor": "☄️ Метеоритный дождь",
    "hellm": "🔥 Адская резня",
    "deathchest": "💀 Сундук смерти",
    "killer_chest": "🗝 Сундук-убийца",
    "beacon_killer": "🗼 Маяк-убийца",
    "killer_beacon": "🗼 Маяк-убийца",
    "bikini": "🏝 Бикини Боттом",
    "bikini_bottom": "🏝 Бикини Боттом",
    "bikinibottom": "🏝 Бикини Боттом",
    "portal": "😈 Адская резня",
    "skull": "💀 Горящий Череп",
    "burning_skull": "💀 Горящий Череп",
    "burningskull": "💀 Горящий Череп",
}

PHASE_NAMES = {
    "RUNNING": "🟢 идёт",
    "ACTIVATING": "🟡 Не открыт",
    "WAITING": "⏳ ожидание",
    "LOOTING": "🎁 открыт",
    "CLOSED": "⚫ закрыт",
    "STARTING": "🟡 скоро",
}

# Редкость лута от меньшей к большей
RARITY_ORDER = ["обычный", "солидный", "богатый", "элитный", "легендарный"]

SORT_NAMES = {
    "anarchy": "по анархии",
    "time": "по времени",
    "rarity": "по редкости",
}


def ctx_line(period: str, sort: str) -> str:
    """Строка заголовка вида '✨ Текущий фильтр - по редкости'."""
    icon = "✨" if period == "current" else "🕐"
    return f"{icon} Текущий фильтр - {SORT_NAMES.get(sort, sort)}"

# Кнопки меню (показываются по шагам, а не все сразу)
BTN_CURRENT = "✨ Текущие ивенты"
BTN_UPCOMING = "🕐 Ближайшие ивенты"
BTN_SYSTEM = "⚙️ Серверные"
BTN_USER = "👤 Ивенты игроков"
BTN_SPOOKY = "🎃 Spooky"
BTN_SORT = "🔀 Сортировка"
BTN_REFRESH = "🔄 Обновить"
BTN_BACK = "◀️ Назад"
BTN_F_ANARCHY = "🖥 По анархии"
BTN_F_TIME = "⏳ По времени"
BTN_F_RARITY = "🎁 По редкости"

STAGE_TYPE, STAGE_PERIOD, STAGE_EVENTS = "type", "period", "events"

PERIODS = ("current", "upcoming")
# Ближайшие = только таймеры "до следующего" (системные без id); всё остальное — текущие

# состояние чата: вид + период + сортировка + id сообщений для чистки
_chat_state: dict[int, dict] = {}


def rarity_rank(loot) -> int:
    """Место редкости в порядке от меньшей к большей. Неизвестная — в конец."""
    if not loot or str(loot).strip().lower() == "null":
        return len(RARITY_ORDER)
    try:
        return RARITY_ORDER.index(str(loot).strip().lower())
    except ValueError:
        return len(RARITY_ORDER)


def time_left(ev: dict) -> int:
    try:
        return max(0, int(ev.get("time-seconds-left") or 0))
    except (TypeError, ValueError):
        return 0


def get_state(chat_id: int) -> dict:
    return _chat_state.setdefault(
        chat_id, {"kind": "system", "period": "current", "sort": "anarchy", "stage": STAGE_TYPE, "events_ids": [], "sort_menu_id": None}
    )

CACHE_TTL = 10
_cache = {"ts": 0, "data": []}

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("funtime-bot")


def server_sort_key(name: str) -> tuple:
    """anarchy101 -> (101, name), чтобы сортировать от меньшей анки к большей."""
    m = re.search(r"(\d+)", str(name))
    num = int(m.group(1)) if m else 10**9
    return (num, str(name))


def server_label(server: str) -> str:
    """anarchy21 -> '<code>21</code> Анархия' (кликабельна только цифра)."""
    m = re.search(r"(\d+)", str(server))
    if m:
        return f"<code>{m.group(1)}</code> Анархия"
    return f"<code>{server}</code>"


def fmt_time(seconds) -> str:
    try:
        s = max(0, int(seconds or 0))
    except (TypeError, ValueError):
        return "—"
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}ч {m}м"
    if m:
        return f"{m}м {sec:02d}с"
    return f"{sec}с"


def fetch_events(force: bool = False):
    now = time.time()
    if not force and now - _cache["ts"] < CACHE_TTL and _cache["data"]:
        return _cache["data"]
    r = requests.get(API_URL, headers=HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json().get("response", [])
    _cache.update(ts=now, data=data)
    return data


def event_display_name(ev: dict) -> str:
    eid = str(ev.get("id") or "")
    return EVENT_NAMES.get(eid, f"❔ {eid}" if eid else "⚙️ Системный")


# У этих ивентов нет координат — проходят на спавне, точку не показываем
NO_COORDS_IDS = {"hellm", "portal"}


def hide_coords(ev: dict) -> bool:
    eid = str(ev.get("id") or "").lower()
    if eid in NO_COORDS_IDS:
        return True
    nm = str(ev.get("name-ru") or EVENT_NAMES.get(eid, "") or "").lower()
    return "адская резня" in nm


def flat_event_line(server: str, ev: dict) -> str:
    """Одна строка для плоских режимов (по времени / по редкости)."""
    eid = ev.get("id")
    name = ev.get("name-ru") or (EVENT_NAMES.get(str(eid), f"❔ {eid}") if eid else "⏳ Таймер")
    line = f"{server_label(server)} • {name} — {fmt_time(ev.get('time-seconds-left', 0))}"
    phase = PHASE_NAMES.get(str(ev.get("phase", "")), "")
    if phase:
        line += f", {phase}"
    loot = ev.get("loot")
    if loot and loot != "null":
        line += f", {loot}"
    if not hide_coords(ev):
        loc = ev.get("location-event")
        if ev.get("location-announced") and isinstance(loc, dict):
            line += f"\n  📍 <code>{loc.get('x')} {loc.get('y')} {loc.get('z')}</code>"
        warp = ev.get("location-warp")
        if warp:
            line += f"\n  📍 <code>{warp}</code>"
    return line


def system_line(server: str, ev: dict) -> str:
    """Одна строка серверного ивента (для режимов по анархии / по времени)."""
    eid = ev.get("id")
    t = fmt_time(ev.get("time-seconds-left", 0))
    if not eid:
        return f"{server_label(server)} — ⏳ до следующего: {t}"
    name = EVENT_NAMES.get(str(eid), f"❔ {eid}")
    phase = PHASE_NAMES.get(str(ev.get("phase", "")), "")
    loot = ev.get("loot")
    extra = ""
    if phase:
        extra += f", {phase}"
    if loot and loot != "null":
        extra += f", лут: {loot}"
    line = f"{server_label(server)} — {name}: {t}{extra}"
    if not hide_coords(ev):
        loc = ev.get("location-event")
        if ev.get("location-announced") and isinstance(loc, dict):
            line += f" 📍 <code>{loc.get('x')} {loc.get('y')} {loc.get('z')}</code>"
    return line


def build_system_text(data, sort: str = "anarchy", period: str = "current") -> str:
    """Серверные ивенты (event-type == system)."""
    rows = []
    for entry in data:
        server = entry.get("server", "?")
        for ev in entry.get("events", []):
            if ev.get("event-type") != "system":
                continue
            rows.append((server, ev))
    if not rows:
        return "😴 Серверных ивентов нет."

    if sort == "time":
        # те же ивенты выбранного периода, но анархии упорядочены по времени
        if period == "current":
            rows = [r for r in rows if r[1].get("id")]
        else:
            rows = [r for r in rows if not r[1].get("id")]
        if not rows:
            if period == "current":
                return "😴 Нет текущих серверных ивентов. Загляни в 🕐 ближайшие."
            return "😴 Нет ближайших серверных ивентов. Загляни в ✨ текущие."
        groups: dict[str, list] = {}
        for server, ev in rows:
            groups.setdefault(server, []).append(ev)
        for evs in groups.values():
            evs.sort(key=time_left)
        ordered = sorted(groups.items(), key=lambda kv: (time_left(kv[1][0]), server_sort_key(kv[0])))
        lines = [f"⚙️ <b>Серверные ивенты</b>\n{ctx_line(period, 'time')}:\n"]
        for server, evs in ordered:
            lines += [system_line(server, e) for e in evs]
        return "\n".join(lines)

    if period == "current":
        # всё с id — уже появившиеся
        rows = [r for r in rows if r[1].get("id")]
    else:
        # только таймеры до следующего
        rows = [r for r in rows if not r[1].get("id")]
    if not rows:
        if period == "current":
            return "😴 Нет текущих серверных ивентов. Загляни в 🕐 ближайшие."
        return "😴 Нет ближайших серверных ивентов. Загляни в ✨ текущие."

    if sort == "rarity":
        rows.sort(key=lambda r: (rarity_rank(r[1].get("loot")), time_left(r[1]), server_sort_key(r[0])))
        lines = [f"⚙️ <b>Серверные ивенты</b>\n{ctx_line(period, 'rarity')}:\n"]
        lines += [flat_event_line(s, e) for s, e in rows]
        return "\n".join(lines)

    rows.sort(key=lambda r: server_sort_key(r[0]))
    lines = [f"⚙️ <b>Серверные ивенты</b>\n{ctx_line(period, 'anarchy')}:\n"]
    for server, ev in rows:
        lines.append(system_line(server, ev))
    return "\n".join(lines)


def render_user_groups(servers: list, header: str) -> str:
    """Групповой вывод по анархиям (для режимов по анархии / по времени)."""
    out = [header]
    for _, server, evs in servers:
        out.append(f"\n🖥 {server_label(server)}")
        # группируем одинаковые id, чтобы myst_beacon x20 не спамил
        grouped = defaultdict(list)
        for e in evs:
            grouped[str(e.get("id", "?"))].append(e)
        for eid, items in grouped.items():
            name = items[0].get("name-ru") or EVENT_NAMES.get(eid, f"❔ {eid}")
            # ближайший по времени первым
            items.sort(key=lambda e: int(e.get("time-seconds-left") or 0))
            if len(items) > 4 and eid == "myst_beacon":
                nearest = fmt_time(items[0].get("time-seconds-left", 0))
                phases = {str(i.get("phase", "")) for i in items}
                ph = ", ".join(PHASE_NAMES.get(p, p) for p in phases)
                out.append(f"  • {name} ×{len(items)} — ближайший через {nearest} ({ph})")
                continue
            for e in items[:8]:  # cap на сервер, чтобы не выйти за лимит ТГ
                phase = PHASE_NAMES.get(str(e.get("phase", "")), str(e.get("phase", "—")))
                t = fmt_time(e.get("time-seconds-left", 0))
                loot = e.get("loot")
                loot_txt = f", лут: {loot}" if loot and loot != "null" else ""
                line = f"  • {name} — {phase}, {t}{loot_txt}"
                if not hide_coords(e):
                    loc = e.get("location-event")
                    if e.get("location-announced") and isinstance(loc, dict):
                        line += f"\n    📍 <code>{loc.get('x')} {loc.get('y')} {loc.get('z')}</code>"
                    warp = e.get("location-warp")
                    if warp:
                        line += f"\n    📍 <code>{warp}</code>"
                out.append(line)
            if len(items) > 8:
                out.append(f"    <i>…и ещё {len(items) - 8}</i>")
    return "\n".join(out)


def build_user_text(data, sort: str = "anarchy", period: str = "current") -> str:
    """Ивенты игроков (event-type == user)."""
    if sort == "rarity":
        if period == "upcoming":
            # у ивентов игроков всегда есть id — все они в текущих
            return "😴 Нет ближайших ивентов игроков. Загляни в ✨ текущие."
        flat = []
        for entry in data:
            server = entry.get("server", "?")
            for e in entry.get("events", []):
                if e.get("event-type") != "user":
                    continue
                flat.append((server, e))
        if not flat:
            return "😴 Нет текущих ивентов игроков. Загляни в 🕐 ближайшие."
        flat.sort(key=lambda r: (rarity_rank(r[1].get("loot")), time_left(r[1]), server_sort_key(r[0])))
        out = [f"👤 <b>Ивенты игроков</b>\n{ctx_line(period, 'rarity')}:\n"]
        out += [flat_event_line(s, e) for s, e in flat]
        return "\n".join(out)

    if sort == "time":
        # те же ивенты выбранной категории, но анархии упорядочены по времени
        if period == "upcoming":
            # у ивентов игроков всегда есть id — все они в текущих
            return "😴 Нет ближайших ивентов игроков. Загляни в ✨ текущие."
        servers = []
        for entry in data:
            server = entry.get("server", "?")
            user_evs = [e for e in entry.get("events", []) if e.get("event-type") == "user"]
            if user_evs:
                user_evs.sort(key=time_left)
                servers.append((server_sort_key(server), server, user_evs))
        if not servers:
            return "😴 Нет текущих ивентов игроков. Попробуй позже / обнови."
        servers.sort(key=lambda x: (min(time_left(e) for e in x[2]), x[0]))
        return render_user_groups(
            servers,
            f"👤 <b>Ивенты игроков</b>\n{ctx_line(period, 'time')}:",
        )

    servers = []
    if period == "upcoming":
        # у ивентов игроков всегда есть id — все они в текущих
        return "😴 Нет ближайших ивентов игроков. Загляни в ✨ текущие."
    for entry in data:
        server = entry.get("server", "?")
        user_evs = [e for e in entry.get("events", []) if e.get("event-type") == "user"]
        if user_evs:
            servers.append((server_sort_key(server), server, user_evs))
    servers.sort(key=lambda x: x[0])
    if not servers:
        return "😴 Нет текущих ивентов игроков. Попробуй позже / обнови."
    return render_user_groups(
        servers,
        f"👤 <b>Ивенты игроков</b>\n{ctx_line(period, 'anarchy')}:",
    )


def sub_gate_menu() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    for ch in CHANNELS:
        kb.add(types.InlineKeyboardButton(ch["label"], url=ch["url"]))
    kb.add(types.InlineKeyboardButton("✅ Проверить", callback_data="sub:check"))
    return kb


def kb_type() -> types.ReplyKeyboardMarkup:
    """Шаг 1: только выбор типа."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, is_persistent=True)
    kb.add(types.KeyboardButton(BTN_SYSTEM), types.KeyboardButton(BTN_USER))
    kb.add(types.KeyboardButton(BTN_SPOOKY))
    return kb


def kb_period() -> types.ReplyKeyboardMarkup:
    """Шаг 2: только выбор периода + назад."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, is_persistent=True)
    kb.add(types.KeyboardButton(BTN_CURRENT), types.KeyboardButton(BTN_UPCOMING))
    kb.add(types.KeyboardButton(BTN_BACK))
    return kb


def kb_events() -> types.ReplyKeyboardMarkup:
    """Шаг 3: только действия с выводом + назад."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, is_persistent=True)
    kb.add(types.KeyboardButton(BTN_SORT), types.KeyboardButton(BTN_REFRESH))
    kb.add(types.KeyboardButton(BTN_BACK))
    return kb


def kb_sort(active: str = "anarchy", period: str = "current") -> types.ReplyKeyboardMarkup:
    """Меню выбора фильтра (кнопки снизу, галочка на активном).
    У ближайших сортировки по редкости нет — у таймеров нет лута."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, is_persistent=True)
    kb.add(
        types.KeyboardButton(("✅ " if active == "anarchy" else "") + BTN_F_ANARCHY),
        types.KeyboardButton(("✅ " if active == "time" else "") + BTN_F_TIME),
    )
    if period != "upcoming":
        kb.add(types.KeyboardButton(("✅ " if active == "rarity" else "") + BTN_F_RARITY))
    kb.add(types.KeyboardButton(BTN_BACK))
    return kb


def send_long(chat_id: int, text: str, reply_markup=None) -> list:
    """Режем длинные тексты под лимит Telegram 4096. Возвращает отправленные сообщения."""
    limit = 4000
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < 0:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:]
    parts.append(text)
    sent = []
    for i, p in enumerate(parts):
        sent.append(bot.send_message(
            chat_id, p, parse_mode="HTML",
            reply_markup=reply_markup if i == len(parts) - 1 else None,
        ))
    return sent


if not BOT_TOKEN:
    raise SystemExit("SET_BOT_TOKEN_ENV")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


def check_subscription(user_id: int) -> bool:
    """True если юзер подписан на ВСЕ каналы. Требует: бот — админ каналов."""
    for ch in CHANNELS:
        try:
            m = bot.get_chat_member(ch["chat_id"], user_id)
            status = getattr(m, "status", "")
            if status in ("creator", "administrator", "member"):
                continue
            # restricted с is_member=True тоже считаем подпиской
            if status == "restricted" and getattr(m, "is_member", False):
                continue
            return False
        except Exception as e:
            log.warning("subcheck fail %s: %s", ch["chat_id"], e)
            return False
    return True


def send_gate(chat_id: int):
    # прячем обычную клавиатуру: остаются только кнопки каналов и "Проверить"
    bot.send_message(chat_id, SUB_GATE_TEXT, reply_markup=types.ReplyKeyboardRemove())
    bot.send_message(chat_id, "👇 Подпишись на оба канала и нажми «Проверить»:", reply_markup=sub_gate_menu())


def delete_messages(chat_id: int, ids) -> None:
    for mid in ids or []:
        try:
            bot.delete_message(chat_id, mid)
        except Exception:
            pass


def is_admin(uid: int) -> bool:
    return bool(ADMIN_IDS) and int(uid or 0) in ADMIN_IDS


def render_spooky(chat_id: int, period: str, force: bool = True) -> None:
    """Spooky через userbot (кеш 40с)."""
    from spooky_provider import get_spooky_text, is_configured as tg_configured
    from spooky_store import get_spooky_manual_text
    st = get_state(chat_id)
    delete_messages(chat_id, st.get("events_ids", []))
    st["events_ids"] = []
    text = ""
    # 1) telethon userbot
    if tg_configured():
        try:
            text = get_spooky_text(period=period, force=force)
            if text.startswith("❌ Ошибка Spooky"):
                raise RuntimeError(text)
        except Exception:
            text = ""
    # 2) http with cookies
    if not text:
        try:
            from spooky_http import is_configured as http_cfg, fetch_spooky_http
            if http_cfg():
                data = fetch_spooky_http()
                # data in funtime format: [{server, events:[...]}] -> reuse system builder
                # spooky servers come as one pool, show as system list
                text = build_system_text(data, sort="anarchy", period="current")
                if period == "upcoming":
                    text = build_system_text(data, sort="anarchy", period="upcoming")
        except Exception as e:
            log.warning("spooky http fail: %s", e)
            text = ""
    # 3) manual forward cache
    if not text:
        text = get_spooky_manual_text(period=period)
    st["kind"] = "spooky"
    st["period"] = period
    st["stage"] = STAGE_EVENTS
    st["events_ids"] = [m.message_id for m in send_long(chat_id, text, reply_markup=kb_events())]


def render_events(chat_id: int, kind: str, sort: str, period: str) -> None:
    """Удаляет старые сообщения с ивентами и отправляет свежие."""
    if kind == "spooky":
        render_spooky(chat_id, period, force=True)
        return
    if period == "upcoming" and sort == "rarity":
        sort = "anarchy"  # у ближайших нет лута — страховка
    st = get_state(chat_id)
    delete_messages(chat_id, st.get("events_ids", []))
    st["events_ids"] = []
    data = fetch_events(force=True)
    if kind == "system":
        text = build_system_text(data, sort, period)
    else:
        text = build_user_text(data, sort, period)
    st["kind"] = kind
    st["sort"] = sort
    st["period"] = period
    st["stage"] = STAGE_EVENTS
    st["events_ids"] = [m.message_id for m in send_long(chat_id, text, reply_markup=kb_events())]


def show_filter_menu(chat_id: int) -> None:
    """Удаляет сообщения с ивентами, показывает меню выбора фильтра."""
    st = get_state(chat_id)
    delete_messages(chat_id, st.get("events_ids", []))
    st["events_ids"] = []
    if st.get("sort_menu_id"):
        delete_messages(chat_id, [st["sort_menu_id"]])
        st["sort_menu_id"] = None
    msg = bot.send_message(chat_id, "Выбери фильтр:", reply_markup=kb_sort(st.get("sort", "anarchy"), st.get("period", "current")))
    st["sort_menu_id"] = msg.message_id


@bot.message_handler(commands=["start", "help", "events"])
def cmd_start(m: types.Message):
    if not check_subscription(m.from_user.id):
        send_gate(m.chat.id)
        return
    get_state(m.chat.id)["stage"] = STAGE_TYPE
    bot.send_message(
        m.chat.id,
        "👋 Привет! Выбери тип ивента:",
        reply_markup=kb_type(),
    )


@bot.message_handler(func=lambda m: bool(m.text) and "Анархия" in m.text, content_types=["text"])
def on_spooky_forward(m: types.Message):
    # ручной режим: только админ может обновлять кеш; остальным показываем кеш
    from spooky_store import save_spooky_raw, get_spooky_manual_text
    if not is_admin(m.from_user.id):
        return
    try:
        n = save_spooky_raw(m.text or "")
        bot.reply_to(m, f"✅ Spooky-кеш обновлен ({n} симв.). Пользователям уже видно по кнопке 🎃 Spooky.")
    except Exception as e:
        bot.reply_to(m, f"❌ Не сохранил: {e}")


@bot.channel_post_handler(func=lambda m: bool(getattr(m, "text", "")) and "Анархия" in m.text, content_types=["text"])
def on_spooky_channel(m: types.Message):
    from spooky_store import save_spooky_raw
    try:
        save_spooky_raw(m.text or "")
        log.info("spooky cache updated from channel")
    except Exception as e:
        log.warning("spooky channel save fail: %s", e)


MENU_BUTTONS = (BTN_CURRENT, BTN_UPCOMING, BTN_SYSTEM, BTN_USER, BTN_SPOOKY, BTN_SORT, BTN_REFRESH, BTN_BACK,
                BTN_F_ANARCHY, BTN_F_TIME, BTN_F_RARITY)


def clean_text(t) -> str:
    """Убирает префикс галочки у кнопок фильтров."""
    return (t or "").removeprefix("✅ ").strip()


@bot.message_handler(func=lambda m: clean_text(m.text) in MENU_BUTTONS)
def on_menu(m: types.Message):
    if not check_subscription(m.from_user.id):
        send_gate(m.chat.id)
        return
    st = get_state(m.chat.id)
    txt = clean_text(m.text)
    if txt in (BTN_SYSTEM, BTN_USER, BTN_SPOOKY):
        # шаг 1 -> шаг 2: выбрали тип, теперь период (ивенты пока не показываем)
        if txt == BTN_SPOOKY:
            st["kind"] = "spooky"
        else:
            st["kind"] = "system" if txt == BTN_SYSTEM else "user"
        st["stage"] = STAGE_PERIOD
        bot.send_message(m.chat.id, "Теперь выбери какие показать:", reply_markup=kb_period())
        return
    if txt in (BTN_CURRENT, BTN_UPCOMING):
        # шаг 2 -> шаг 3: выбрали период, показываем ивенты
        st["period"] = "current" if txt == BTN_CURRENT else "upcoming"
        if st.get("kind") == "spooky":
            try:
                render_spooky(m.chat.id, st["period"], force=False)
            except Exception as e:
                log.exception("spooky failed")
                bot.send_message(m.chat.id, f"❌ Ошибка Spooky: {e}")
            return
        if st["period"] == "upcoming" and st.get("sort") == "rarity":
            # у ближайших нет сортировки по редкости — откатываем на анархию
            st["sort"] = "anarchy"
        try:
            render_events(m.chat.id, st.get("kind", "system"), st.get("sort", "anarchy"), st["period"])
        except Exception as e:
            log.exception("fetch failed")
            bot.send_message(m.chat.id, f"❌ Ошибка API: {e}")
        return
    if txt in (BTN_F_ANARCHY, BTN_F_TIME, BTN_F_RARITY):
        # выбрали фильтр в меню — закрываем его и показываем ивенты
        mode = {"🖥": "anarchy", "⏳": "time", "🎁": "rarity"}[txt[0]]
        if mode == "rarity" and st.get("period") == "upcoming":
            bot.send_message(
                m.chat.id,
                "⛔ Для ближайших сортировка по редкости недоступна — у таймеров нет лута.",
                reply_markup=kb_sort(st.get("sort", "anarchy"), "upcoming"),
            )
            return
        st["sort"] = mode
        if st.get("sort_menu_id"):
            delete_messages(m.chat.id, [st["sort_menu_id"]])
            st["sort_menu_id"] = None
        try:
            render_events(m.chat.id, st.get("kind", "system"), st["sort"], st.get("period", "current"))
        except Exception as e:
            log.exception("fetch failed")
            bot.send_message(m.chat.id, f"❌ Ошибка API: {e}")
        return
    if txt == BTN_BACK:
        if st.get("sort_menu_id"):
            # назад из меню фильтров — возвращаемся к ивентам
            delete_messages(m.chat.id, [st["sort_menu_id"]])
            st["sort_menu_id"] = None
            try:
                render_events(m.chat.id, st.get("kind", "system"), st.get("sort", "anarchy"), st.get("period", "current"))
            except Exception as e:
                log.exception("fetch failed")
                bot.send_message(m.chat.id, f"❌ Ошибка API: {e}")
        elif st.get("stage") == STAGE_EVENTS:
            st["stage"] = STAGE_PERIOD
            bot.send_message(m.chat.id, "Теперь выбери какие показать:", reply_markup=kb_period())
        else:
            st["stage"] = STAGE_TYPE
            bot.send_message(m.chat.id, "Выбери тип ивента:", reply_markup=kb_type())
        return
    if txt == BTN_SORT:
        show_filter_menu(m.chat.id)
        return
    try:
        if st.get("kind") == "spooky":
            render_spooky(m.chat.id, st.get("period", "current"), force=True)
        else:
            render_events(m.chat.id, st.get("kind", "system"), st.get("sort", "anarchy"), st.get("period", "current"))
    except Exception as e:
        log.exception("fetch failed")
        bot.send_message(m.chat.id, f"❌ Ошибка API: {e}")


@bot.callback_query_handler(func=lambda c: c.data == "sub:check")
def cb_sub_check(c: types.CallbackQuery):
    if check_subscription(c.from_user.id):
        bot.answer_callback_query(c.id, "✅ Подписка подтверждена!")
        get_state(c.message.chat.id)["stage"] = STAGE_TYPE
        bot.send_message(
            c.message.chat.id,
            "👋 Привет! Выбери тип ивента:",
            reply_markup=kb_type(),
        )
    else:
        bot.answer_callback_query(c.id, "❌ Ты ещё не подписался на все каналы", show_alert=True)


@bot.callback_query_handler(func=lambda c: c.data and (c.data.startswith("ev:") or c.data.startswith("nav:")))
def cb_events(c: types.CallbackQuery):
    if not check_subscription(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Сначала подпишись на каналы", show_alert=True)
        send_gate(c.message.chat.id)
        return
    chat_id = c.message.chat.id
    st = get_state(chat_id)

    if c.data == "nav:sort":
        bot.answer_callback_query(c.id)
        show_filter_menu(chat_id)
        return

    kind = c.data.split(":", 1)[1]
    if kind == "menu":
        bot.answer_callback_query(c.id)
        delete_messages(chat_id, st.get("events_ids", []))
        st["events_ids"] = []
        if st.get("sort_menu_id"):
            delete_messages(chat_id, [st["sort_menu_id"]])
            st["sort_menu_id"] = None
        st["stage"] = STAGE_TYPE
        bot.send_message(chat_id, "Выбери тип ивента:", reply_markup=kb_type())
        return

    if kind == "refresh":
        bot.answer_callback_query(c.id, "⏳ Загружаю…")
        try:
            if st.get("kind") == "spooky":
                render_spooky(chat_id, st.get("period", "current"), force=True)
            else:
                render_events(chat_id, st.get("kind", "system"), st.get("sort", "anarchy"), st.get("period", "current"))
        except Exception as e:
            log.exception("fetch failed")
            bot.send_message(chat_id, f"❌ Ошибка API: {e}")
        return

    # ev:system / ev:user — выбор вида (в т.ч. старые кнопки-переключатели)
    st["kind"] = kind
    if st.get("sort_menu_id"):
        delete_messages(chat_id, [st["sort_menu_id"]])
        st["sort_menu_id"] = None
    bot.answer_callback_query(c.id, "⏳ Загружаю…")
    try:
        render_events(chat_id, kind, st.get("sort", "anarchy"), st.get("period", "current"))
    except Exception as e:
        log.exception("fetch failed")
        bot.send_message(chat_id, f"❌ Ошибка API: {e}")
    return


if __name__ == "__main__":
    raise SystemExit("Эта сборка только для webhook: запускай через gunicorn webhook:app")

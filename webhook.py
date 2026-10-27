"""Webhook-режим для хостингов (PandaStack, Render и т.п.). Polling'а тут нет.

Запуск локально:   python webhook.py
На хостинге:       gunicorn webhook:app --bind 0.0.0.0:$PORT --workers 1 --threads 8

Env:
  BOT_TOKEN    - обязательно, токен из BotFather
  WEBHOOK_URL  - публичный адрес приложения без слэша на конце
                 (если не задан, бот возьмёт адрес из первого GET-запроса
                 к "/" по публичному домену)

После деплоя достаточно открыть публичный URL приложения в браузере -
webhook зарегистрируется сам. Если задан WEBHOOK_URL, он ставится при старте.
Регистрация идёт в фоновом потоке, чтобы не тормозить health-check хостинга.
"""
import os
import threading

from flask import Flask, abort, request
import telebot

import bot as botmod

TOKEN = os.getenv("BOT_TOKEN", "").strip()
PUBLIC_URL = os.getenv("WEBHOOK_URL", "").strip().rstrip("/")

app = Flask(__name__)

_lock = threading.Lock()
_registered = False
_pending = False


def _public_base() -> str:
    """Публичный базовый URL: WEBHOOK_URL или заголовки обратного прокси."""
    if PUBLIC_URL:
        return PUBLIC_URL
    proto = request.headers.get("X-Forwarded-Proto") or request.scheme
    host = (request.headers.get("X-Forwarded-Host") or request.host or "").split(",")[0].strip()
    if not host or "." not in host:
        return ""
    if host.startswith(("localhost", "127.0.0.1", "0.0.0.0", "10.", "192.168.")):
        return ""
    return f"{proto}://{host}"


def _set_webhook(base: str) -> None:
    global _registered, _pending
    try:
        if not TOKEN or not base or _registered:
            return
        with _lock:
            if _registered:
                return
            url = f"{base}/{TOKEN}"
            info = botmod.bot.get_webhook_info()
            if getattr(info, "url", "") != url:
                botmod.bot.set_webhook(url=url, allowed_updates=None)
            _registered = True
            botmod.log.info("webhook set to %s", base)
    except Exception as e:  # noqa: BLE001
        botmod.log.warning("webhook setup failed: %s", e)
    finally:
        _pending = False


def _kick_webhook(base: str) -> None:
    """Запускает регистрацию webhook в фоне, не блокируя HTTP-ответ."""
    global _pending
    if not TOKEN or not base or _registered or _pending:
        return
    with _lock:
        if _registered or _pending:
            return
        _pending = True
    threading.Thread(target=_set_webhook, args=(base,), daemon=True).start()


@app.route("/", methods=["GET"])
def index():
    _kick_webhook(_public_base())
    return "ok", 200


@app.route("/health", methods=["GET"])
def health():
    return {"ok": True}, 200


@app.route(f"/{TOKEN}", methods=["POST"])
def updates():
    if not TOKEN:
        return abort(403)
    try:
        upd = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    except Exception:
        return abort(400)
    botmod.bot.process_new_updates([upd])
    return "ok", 200


if TOKEN and PUBLIC_URL:
    _kick_webhook(PUBLIC_URL)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), threaded=True)

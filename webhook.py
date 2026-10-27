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


def _ensure_webhook(base: str) -> None:
    """Ставит webhook один раз за жизнь процесса. Ошибки не роняют приложение."""
    global _registered
    if not TOKEN or not base or _registered:
        return
    with _lock:
        if _registered:
            return
        url = f"{base}/{TOKEN}"
        try:
            info = botmod.bot.get_webhook_info()
            if getattr(info, "url", "") == url:
                _registered = True
                botmod.log.info("webhook already set to %s", base)
                return
            botmod.bot.remove_webhook()
            botmod.bot.set_webhook(url=url, allowed_updates=None)
            _registered = True
            botmod.log.info("webhook set to %s", base)
        except Exception as e:  # noqa: BLE001
            botmod.log.warning("webhook setup failed: %s", e)


@app.route("/", methods=["GET"])
def index():
    _ensure_webhook(_public_base())
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
    # На хостинге с WEBHOOK_URL регистрируем сразу, не дожидаясь запроса.
    with app.app_context():
        try:
            botmod.bot.remove_webhook()
            botmod.bot.set_webhook(url=f"{PUBLIC_URL}/{TOKEN}", allowed_updates=None)
            _registered = True
            botmod.log.info("webhook set to %s", PUBLIC_URL)
        except Exception as e:  # noqa: BLE001
            botmod.log.warning("webhook setup failed: %s", e)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), threaded=True)

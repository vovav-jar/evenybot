"""Только webhook-режим (Render Web Service и т.п.). Polling'а тут нет.

Для Render:
  Build Command:  pip install -r requirements.txt
  Start Command:  gunicorn webhook:app --bind 0.0.0.0:$PORT --workers 1
  Env vars:       BOT_TOKEN, WEBHOOK_URL=https://<имя>.onrender.com
  (WEBHOOK_URL без слэша на конце)

Нюансы бесплатного Render: без входящих сервис засыпает через ~15 мин,
первое сообщение после сна идёт с задержкой (холодный старт ~30-60 сек).
"""
import os
import time

from flask import Flask, request, abort
import telebot

import bot as botmod

TOKEN = os.getenv("BOT_TOKEN", "").strip()

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    return "ok", 200


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


if TOKEN:
    public = os.getenv("WEBHOOK_URL", "").rstrip("/")
    if public:
        botmod.bot.remove_webhook()
        time.sleep(1)
        botmod.bot.set_webhook(url=f"{public}/{TOKEN}")
        botmod.log.info("webhook set to %s", public)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))

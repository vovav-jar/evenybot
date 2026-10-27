# FtSpEventBot

Telegram-бот с ивентами FunTime (funtime.me API) + Spooky.

## Деплой на PandaStack

1. Репозиторий на GitHub должен быть **публичным** (или подключён GitHub App).
2. В панели PandaStack создать приложение из Git:
   - **Git URL:** `https://github.com/<логин>/FtSpEventBot`
   - **Branch:** `master` (или `main` — как называется ветка)
   - **Runtime:** Python, версия `3.12`
   - **Install command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn webhook:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120`
   - **Port:** `3000`
3. Env-переменные приложения:
   - `BOT_TOKEN` — токен из @BotFather (**обязательно**)
   - `ADMIN_IDS` — Telegram ID админов через запятую (необязательно)
   - `WEBHOOK_URL` — публичный URL приложения, без слэша на конце (необязательно:
     если не задан, бот зарегистрирует webhook сам при первом открытии URL)
   - `SPOOKY_URL`, `SPOOKY_URL2`, `FT_COOKIE` — необязательно, для Spooky по HTTP
   - `API_ID`, `API_HASH`, `SESSION_STRING`, `SPOOKY_BOT` — необязательно, для Spooky через Telethon
4. Deploy → дождаться статуса `live` → открыть публичный URL приложения в браузере.
   Должно появиться `ok`, а в логах — `webhook set to ...`.

Конфиг деплоя продублирован в `pandastack.json`, поэтому команды можно не вбивать вручную.

## Локальный запуск

Polling (как раньше, без публичного URL):

```
pip install -r requirements.txt
set BOT_TOKEN=...
python main.py
```

Webhook (как на хостинге):

```
set BOT_TOKEN=...
set WEBHOOK_URL=https://ваш-домен
python webhook.py
```

## Файлы

- `bot.py` — логика бота, хендлеры
- `main.py` — polling-запуск
- `webhook.py` — webhook-запуск (Flask + gunicorn)
- `spooky_store.py` / `spooky_provider.py` / `spooky_http.py` — Spooky
- `spooky_bridge.py`, `gen_session.py`, `test_cookie.py` — локальные вспомогательные
  скрипты, на хостинге не нужны

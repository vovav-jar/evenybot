"""Spooky via HTTP with login cookies (no Telethon, no API_ID).
Use when spooky events are on a site/API that needs login.

ENV:
  SPOOKY_URL   full JSON URL, e.g. https://funtime.me/api/backend/api/v1/events?event-type=all&server-type=all
               or spookytime site endpoint you find in F12 -> Network
  FT_COOKIE    full Cookie header copied from browser after login
               e.g. session=abc; token=xyz; ...
  SPOOKY_URL2  optional second URL to try (fallback)

How to get URL + cookies:
  1. Login in Chrome to site where spooky events visible.
  2. F12 -> Network -> reload page -> find XHR with events JSON.
  3. Click it -> Headers -> Copy Cookie header -> paste to FT_COOKIE.
  4. Copy Request URL -> paste to SPOOKY_URL.
"""
import os
import logging
import requests

log = logging.getLogger("spooky_http")

SPOOKY_URL = os.getenv("SPOOKY_URL", "").strip()
SPOOKY_URL2 = os.getenv("SPOOKY_URL2", "").strip()
FT_COOKIE = os.getenv("FT_COOKIE", "").strip()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Accept": "application/json, */*",
    "Referer": "https://funtime.me/events",
}


def is_configured() -> bool:
    return bool(SPOOKY_URL)


def fetch_spooky_http():
    urls = [u for u in (SPOOKY_URL, SPOOKY_URL2) if u]
    if not urls:
        raise RuntimeError("SPOOKY_URL не задан")
    headers = dict(HEADERS)
    if FT_COOKIE:
        headers["Cookie"] = FT_COOKIE
    last_err = None
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            j = r.json()
            data = j.get("response", j)
            if isinstance(data, dict):
                data = [data]
            return data
        except Exception as e:
            last_err = e
            log.warning("spooky http fail %s: %s", url, e)
            continue
    raise RuntimeError(f"HTTP fetch failed: {last_err}")

"""Generate SESSION_STRING for extra Telegram account (Telethon).
Run locally:  python gen_session.py
Enter phone, code, 2FA password if asked. Output SESSION_STRING -> paste to hosting Env.
"""
import os

try:
    from telethon.sessions import StringSession
    from telethon import TelegramClient
except ImportError:
    raise SystemExit("need: pip install telethon")

API_ID = input("API_ID (my.telegram.org): ").strip()
API_HASH = input("API_HASH: ").strip()

if not API_ID or not API_HASH:
    raise SystemExit("API_ID/HASH required")

with TelegramClient(StringSession(), int(API_ID), API_HASH) as client:
    s = client.session.save()
    print("\n=== SESSION_STRING (copy to hosting Env) ===")
    print(s)
    print("=== end ===")

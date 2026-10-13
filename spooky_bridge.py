"""Spooky bridge without API_ID. Uses Telegram Web session (cookies), not MTProto.
Runs on your PC (must stay on). Every 60s reads SpookyTimeBot wall and sends it
to your bot as admin - your bot saves it via on_spooky_forward handler.

Setup:
  pip install playwright
  playwright install chromium   (once)
  python spooky_bridge.py       (first run: login to Telegram Web with EXTRA account)

Config via env or edit below:
  SPOOKY_SOURCE = @username of source bot (e.g. @SpookyTimeBot)
  MY_BOT        = @username of your bot (e.g. @FtSpEventBot)
  BOT_TOKEN     = not needed here
"""
import os
import re
import time

SPOOKY_SOURCE = os.getenv("SPOOKY_SOURCE", "@SpookyTimeBot")
MY_BOT = os.getenv("MY_BOT", "@FtSpEventBot")
POLL_SEC = int(os.getenv("BRIDGE_POLL", "60") or 60)

def extract_wall(body_text: str) -> str:
    # wall = chunk containing many "Анархия N:" - take from first Анархия to end
    m = body_text.find("Анархия")
    if m < 0:
        return ""
    wall = body_text[m:].strip()
    # cut UI tail (Message input, Search, etc.)
    for tail in ("\nMessage\n", "\nСообщение\n", "\nSearch\n", "\nПоиск\n"):
        if tail in wall:
            wall = wall.split(tail)[0]
    return wall[:12000].strip()

def main():
    from playwright.sync_api import sync_playwright
    print("source:", SPOOKY_SOURCE, "-> my bot:", MY_BOT)
    print("profile dir: ./tg-profile (first run will ask login)")
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir="./tg-profile",
            headless=False,  # first login visible; later can set True
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page() if not ctx.pages else ctx.pages[0]
        page.goto("https://web.telegram.org/k/", wait_until="domcontentloaded")
        print(">>> If you see login screen: login with EXTRA account (phone/QR), then press Enter here.")
        try:
            input("Press Enter when Telegram Web is logged in and chats loaded...")
        except EOFError:
            pass
        last_sent = ""
        while True:
            try:
                page.goto(f"https://web.telegram.org/k/#{SPOOKY_SOURCE}", wait_until="domcontentloaded")
                page.wait_for_timeout(6000)
                body = page.inner_text("body")
                wall = extract_wall(body)
                if not wall or "Анархия" not in wall:
                    print("no wall yet, retry in", POLL_SEC)
                    time.sleep(POLL_SEC)
                    continue
                if wall == last_sent:
                    print("same wall, skip")
                    time.sleep(POLL_SEC)
                    continue
                # send wall to own bot as user message
                page.goto(f"https://web.telegram.org/k/#{MY_BOT}", wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                # message box: contenteditable div
                box = page.locator('div[contenteditable="true"]').last
                # split long text (Telegram Web limit per message ~4096)
                chunk = wall[:3900]
                box.click()
                box.fill(chunk)
                page.wait_for_timeout(500)
                page.keyboard.press("Enter")
                page.wait_for_timeout(2000)
                print(f"sent wall {len(chunk)} chars")
                last_sent = wall
            except Exception as e:
                print("bridge error:", e)
            time.sleep(POLL_SEC)

if __name__ == "__main__":
    main()

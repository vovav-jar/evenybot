"""Test FT_COOKIE against funtime API. Run: python test_cookie.py
Paste cookie when asked (not in chat). Checks if spooky servers appear.
"""
import requests

URLS = [
    "https://funtime.me/api/backend/api/v1/events?event-type=all&server-type=",
    "https://funtime.me/api/backend/api/v1/events?event-type=all&server-type=all",
]

cookie = input("FT_COOKIE (full Cookie header value): ").strip()
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Accept": "application/json, */*",
    "Referer": "https://funtime.me/events",
}
if cookie:
    headers["Cookie"] = cookie

for url in URLS:
    print("\nGET", url)
    try:
        r = requests.get(url, headers=headers, timeout=15)
        print("status:", r.status_code)
        j = r.json()
        resp = j.get("response", [])
        print("servers:", len(resp))
        ids = set()
        for entry in resp[:200]:
            for ev in entry.get("events", []):
                if ev.get("id"):
                    ids.add(str(ev.get("id")))
        print("ids found:", sorted(ids)[:30])
        spooky_marks = [i for i in ids if i.lower() in ("bikini", "bikini_bottom", "portal", "skull", "burning_skull", "beacon_killer", "killer_beacon")]
        print("spooky ids:", spooky_marks if spooky_marks else "none - cookie doesn't unlock spooky")
    except Exception as e:
        print("fail:", e)

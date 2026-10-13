"""Polling entrypoint for bot-hosting.net (Pterodactyl).
Startup File in panel must be: main.py
ENV in panel: BOT_TOKEN=<token from BotFather>
"""
import logging
import time

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("main")

import bot as botmod

if __name__ == "__main__":
    log.info("starting polling...")
    while True:
        try:
            botmod.bot.infinity_polling(
                skip_pending=True,
                timeout=30,
                long_polling_timeout=30,
                allowed_updates=None,
            )
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.exception("polling crashed: %s", e)
            time.sleep(5)

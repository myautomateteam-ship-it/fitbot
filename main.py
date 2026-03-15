import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.handlers import main as bot_main, bot
from bot.scheduler import run_scheduler


async def main():
    print("🚀 FitBot v2 запускается...")
    await asyncio.gather(
        bot_main(),
        run_scheduler()
    )


if __name__ == "__main__":
    asyncio.run(main())

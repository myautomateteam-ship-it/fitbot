import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from bot.handlers import router
from bot.services.scheduler import run_scheduler
from bot.handlers.common import main_menu, energy_kb

load_dotenv(dotenv_path="config/.env")


async def main():
    print("🤖 FitBot v3 запущен!")
    bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
    dp  = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    asyncio.create_task(run_scheduler(bot, energy_kb, main_menu))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

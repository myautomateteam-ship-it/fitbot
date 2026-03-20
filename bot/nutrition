from aiogram import Router
from aiogram.types import Message

from bot.db import log_food, today_food, get_profile
from bot.services.ai import ai_kbju
from bot.handlers.common import main_menu

router = Router()


async def handle_food(message: Message, user: dict, text: str):
    await message.answer("⏳ Считаю КБЖУ...")
    uid = user["id"]
    n = await ai_kbju(text)

    if not n:
        await message.answer("Не смог посчитать. Опиши подробнее 🙏", reply_markup=main_menu())
        return

    log_food(uid, text, n["calories"], n["protein"], n["fat"], n["carbs"],
             n.get("is_approximate", False))

    updated = today_food(uid)
    profile = get_profile(uid)
    dc  = (profile or {}).get("daily_calories") or 2000
    dp  = (profile or {}).get("daily_protein")  or 150
    rem = dc - updated["calories"]
    a   = "~" if n.get("is_approximate") else ""

    await message.answer(
        f"✅ {n.get('description', text)}\n\n"
        f"🔥 {a}{n['calories']} ккал | "
        f"🥩 Б:{a}{n['protein']}г | "
        f"🥑 Ж:{a}{n['fat']}г | "
        f"🍞 У:{a}{n['carbs']}г\n\n"
        f"━━━━━━━━\n"
        f"📈 За день: {round(updated['calories'])} / {round(dc)} ккал\n"
        f"{'✅' if rem > 0 else '⚠️'} Осталось: {round(rem)} ккал | "
        f"Белок: {round(dp - updated['protein'])}г",
        reply_markup=main_menu()
    )

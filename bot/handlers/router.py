from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from bot.db import (
    get_user, update_user, get_profile, set_sleep, calc_sleep,
    save_checkin, get_all_users
)
from bot.db.client import sb
from bot.handlers.chat import router as chat_router, handle_ai_message
from bot.handlers.nutrition import handle_food
from bot.handlers.menu import (
    handle_workout, handle_progress,
    handle_schedule, handle_profile_view
)
from bot.handlers.common import main_menu, energy_kb, SLEEP_WORDS, FOOD_WORDS
from datetime import datetime

router = Router()
router.include_router(chat_router)


@router.message(F.text)
async def handle_all(message: Message):
    tg_id = message.from_user.id
    text  = message.text.strip()
    user  = get_user(tg_id)

    if not user:
        from bot.handlers.chat import cmd_start
        await cmd_start(message)
        return

    if user.get("status") == "banned":
        await message.answer("🚫 Аккаунт заблокирован.")
        return

    update_user(tg_id, {"last_active": datetime.utcnow().isoformat()})

    # Идёт спать
    if any(w in text.lower() for w in SLEEP_WORDS):
        set_sleep(tg_id)
        await handle_ai_message(message, user, text)
        return

    # Кнопки меню
    if text == "💪 Тренировка":
        await handle_workout(message, user); return
    if text == "🥗 Питание":
        await message.answer("🥗 Напиши что съел — посчитаю КБЖУ!", reply_markup=main_menu()); return
    if text == "📊 Прогресс":
        await handle_progress(message, user); return
    if text == "📅 Расписание":
        await handle_schedule(message, user); return
    if text == "⚙️ Профиль":
        await handle_profile_view(message, user); return
    if text == "💬 Спросить Макса":
        await message.answer("Задай любой вопрос! 💬", reply_markup=main_menu()); return

    # Еда
    if any(w in text.lower() for w in FOOD_WORDS):
        await handle_food(message, user, text); return

    # AI чат
    await handle_ai_message(message, user, text)


@router.callback_query(F.data.startswith("e_"))
async def cb_energy(callback: CallbackQuery):
    level = int(callback.data.split("_")[1])
    user  = get_user(callback.from_user.id)
    if not user: return
    uid = user["id"]
    save_checkin(uid, {"energy_level": level})
    sleep_h = calc_sleep(uid, callback.from_user.id)

    words = {1: "Понял, бережём силы 🙏", 3: "Хорошо!", 5: "Огонь! 🔥"}
    msg = words.get(level, "Записал!")
    if sleep_h:
        msg += f"\n😴 Поспал {sleep_h} ч — {'маловато' if sleep_h < 6 else 'хорошо!'}"

    await callback.message.edit_text(msg)
    await callback.message.answer("Чем займёмся?", reply_markup=main_menu())


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    user = get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin", "superadmin"]: return
    from bot.db.users import get_stats
    s = get_stats()
    await message.answer(
        f"👑 Админ\n\n"
        f"👥 Всего: {s['total']} | ✅ Активных: {s['active']} | 📋 С анкетой: {s['onboarded']}\n\n"
        f"/ban [id] | /unban [id] | /broadcast [текст]"
    )


@router.message(Command("ban"))
async def cmd_ban(message: Message):
    user = get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin", "superadmin"]: return
    args = message.text.split()
    if len(args) < 2: await message.answer("/ban [id]"); return
    sb.table("users").update({"status": "banned"}).eq("telegram_id", int(args[1])).execute()
    await message.answer(f"✅ Забанен {args[1]}")


@router.message(Command("unban"))
async def cmd_unban(message: Message):
    user = get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin", "superadmin"]: return
    args = message.text.split()
    if len(args) < 2: await message.answer("/unban [id]"); return
    sb.table("users").update({"status": "active"}).eq("telegram_id", int(args[1])).execute()
    await message.answer(f"✅ Разбанен {args[1]}")


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    import asyncio
    user = get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin", "superadmin"]: return
    text = message.text.replace("/broadcast", "").strip()
    if not text: await message.answer("/broadcast [текст]"); return
    from aiogram import Bot
    bot = Bot.get_current()
    users = get_all_users("active")
    sent = 0
    for u in users:
        try:
            await bot.send_message(u["telegram_id"], text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await message.answer(f"✅ Отправлено: {sent}/{len(users)}")

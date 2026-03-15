import os
import asyncio
from datetime import datetime, date
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from database.db import *
from bot.ai_service import *

load_dotenv(dotenv_path="config/.env")

bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
dp = Dispatcher(storage=MemoryStorage())

ONBOARDING_QUESTIONS = {
    "ask_age":        "Сколько тебе лет?",
    "ask_gender":     "Ты парень или девушка?",
    "ask_height":     "📏 Рост в сантиметрах? (например: 178)",
    "ask_weight":     "⚖️ Вес сейчас в кг? (например: 75)",
    "ask_target":     "🎯 Целевой вес? (или «не знаю»)",
    "ask_goal":       "Главная цель?\n\n🔥 Похудеть\n💪 Набрать массу\n⚖️ Поддержать форму\n❤️ Здоровье",
    "ask_experience": "Опыт тренировок?\n\n🌱 Новичок\n📈 Средний\n🚀 Продвинутый",
    "ask_days":       "Сколько дней в неделю готов тренироваться?",
    "ask_duration":   "Сколько минут на одну тренировку? (например: 60)",
    "ask_equipment":  "Где тренируешься?\n\n🏠 Дома\n🏋️ В зале\n🔄 И там и там",
    "ask_wake_time":  "⏰ Во сколько обычно просыпаешься? (например: 08:00)",
    "ask_work":       "Работа — сидячая, активная или смешанная? (или «нет работы»)",
    "ask_injuries":   "🩺 Есть травмы или ограничения? (или «нет»)",
    "ask_diet":       "Особенности питания?\n🍖 Стандарт / 🥦 Вегетарианство / 🌱 Веганство / 🥑 Кето / 🔄 Другое",
    "ask_allergies":  "Аллергии на продукты? (или «нет»)",
    "ask_style":      "Как удобнее общаться?\n😊 Дружелюбно / 💪 Строго / 😄 С юмором",
}

SLEEP_WORDS = ["спокойной ночи", "сплю", "иду спать", "ложусь", "спать", "ночи"]

def main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💪 Тренировка"), KeyboardButton(text="🥗 Питание")],
        [KeyboardButton(text="📊 Прогресс"), KeyboardButton(text="📅 Расписание")],
        [KeyboardButton(text="⚙️ Профиль"), KeyboardButton(text="❓ Спросить Макса")]
    ], resize_keyboard=True)

def confirm_kb(pid: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Сохранить", callback_data=f"confirm_{pid}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_{pid}")
    ]])

def energy_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="😴 Плохо", callback_data="energy_1"),
        InlineKeyboardButton(text="😐 Нормально", callback_data="energy_3"),
        InlineKeyboardButton(text="⚡ Отлично", callback_data="energy_5"),
    ]])

def workout_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💪 Полная", callback_data="workout_full"),
        InlineKeyboardButton(text="⚡ Лёгкая", callback_data="workout_light"),
        InlineKeyboardButton(text="❌ Пропустить", callback_data="workout_skip"),
    ]])


@dp.message(CommandStart())
async def cmd_start(message: Message):
    tg = message.from_user
    user = await get_user(tg.id)
    if not user:
        user = await create_user(tg.id, tg.username, tg.first_name, tg.last_name)
        await update_user(tg.id, {"onboarding_step": "ask_age"})
        await message.answer(
            f"👋 Привет, {tg.first_name}! Я Макс — твой личный тренер.\n\nДавай познакомимся!\n\n{ONBOARDING_QUESTIONS['ask_age']}",
            reply_markup=ReplyKeyboardRemove()
        )
    elif not user.get("onboarding_done"):
        step = user.get("onboarding_step", "ask_age")
        await message.answer(f"Продолжим! 😊\n\n{ONBOARDING_QUESTIONS.get(step,'Введи данные:')}", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer(f"С возвращением, {tg.first_name}! 💪 Чем займёмся?", reply_markup=main_menu())


@dp.message(F.text)
async def handle_message(message: Message):
    tg_id = message.from_user.id
    text = message.text.strip()
    user = await get_user(tg_id)
    if not user:
        await cmd_start(message)
        return
    if user.get("status") == "banned":
        await message.answer("🚫 Аккаунт заблокирован.")
        return
    await update_user(tg_id, {"last_active": datetime.utcnow().isoformat()})
    if not user.get("onboarding_done"):
        await handle_onboarding(message, user, text)
        return
    if any(w in text.lower() for w in SLEEP_WORDS):
        await set_sleep_time(tg_id)
        await message.answer("Спокойной ночи! 😴 Запомнил время — утром скажу сколько поспал.", reply_markup=main_menu())
        return
    if text == "💪 Тренировка":
        await handle_workout(message, user)
    elif text == "🥗 Питание":
        await message.answer("🥗 Напиши что съел — посчитаю КБЖУ!\n\nНапример: «съел 3 яйца и тост»", reply_markup=main_menu())
    elif text == "📊 Прогресс":
        await handle_progress(message, user)
    elif text == "📅 Расписание":
        await handle_schedule(message, user)
    elif text == "⚙️ Профиль":
        await handle_profile(message, user)
    elif text == "❓ Спросить Макса":
        await message.answer("Задай любой вопрос! 💬", reply_markup=main_menu())
    else:
        food_words = ["съел","съела","выпил","выпила","поел","поела","перекус","завтрак","обед","ужин","скушал"]
        if any(w in text.lower() for w in food_words):
            profile = await get_profile(user["id"])
            today = await get_today_nutrition(user["id"])
            await handle_food_log(message, user, text, profile, today)
        else:
            extracted = await extract_data(text)
            await handle_ai_chat(message, user, text, extracted)


async def handle_ai_chat(message: Message, user: dict, text: str, extracted: dict):
    profile = await get_profile(user["id"])
    today = await get_today_nutrition(user["id"])
    checkin = await get_today_checkin(user["id"])
    pat_res = supabase.table("user_patterns").select("*").eq("user_id", user["id"]).execute()
    patterns = pat_res.data[0] if pat_res.data else None
    notes = await get_notes(user["id"])
    if extracted.get("weight_update"):
        w = extracted["weight_update"]
        old_w = (profile or {}).get("weight")
        preview = f"📊 Обновление веса:\nБыло: {old_w or '?'} кг → Стало: {w} кг"
        if old_w and abs(float(old_w) - float(w)) > 10:
            preview = f"⚠️ Большое изменение!\nБыло: {old_w} кг → Стало: {w} кг\n\nЭто точно?"
        pending = await create_pending(message.from_user.id, user["id"], "weight", {"weight": w}, preview)
        if pending:
            await message.answer(preview, reply_markup=confirm_kb(pending["id"]))
            return
    if extracted.get("preference"):
        await save_note(user["id"], "preference", f"pref_{int(datetime.now().timestamp())}", extracted["preference"], text)
    if extracted.get("custom_note"):
        await save_note(user["id"], "context", f"note_{int(datetime.now().timestamp())}", extracted["custom_note"], text)
    today_data = {**(today or {}), **(checkin or {})}
    await message.answer("...")
    reply = await chat(user["id"], text, profile, today_data, patterns, notes)
    await message.answer(reply, reply_markup=main_menu())


async def handle_onboarding(message: Message, user: dict, text: str):
    step = user.get("onboarding_step", "ask_age")
    result = await process_onboarding(step, text)
    if not result.get("valid"):
        await message.answer(result.get("reply", "Попробуй ещё раз 😊"))
        return
    field = result["field"]
    value = result["value"]
    if field in ["age","height","days_per_week","session_duration","activity_level"]:
        try: value = int(float(value))
        except: pass
    elif field in ["weight","target_weight"]:
        try: value = float(value)
        except: value = None
    elif field in ["injuries","food_allergies"]:
        if isinstance(value, str):
            if value.lower() in ["нет","no","none","[]",""]:
                value = []
            else:
                value = [v.strip() for v in value.replace("[","").replace("]","").split(",")]
    if value is not None:
        await update_profile(user["id"], {field: value})
    next_step = result.get("next_state", "completed")
    if next_step == "completed":
        await finish_onboarding(message, user)
    else:
        await update_user(message.from_user.id, {"onboarding_step": next_step})
        await message.answer(f"✅ Записал!\n\n{ONBOARDING_QUESTIONS.get(next_step,'')}")


async def finish_onboarding(message: Message, user: dict):
    profile = await get_profile(user["id"])
    nutrition_text = ""
    if all([profile.get("age"), profile.get("gender"), profile.get("height"),
            profile.get("weight"), profile.get("activity_level"), profile.get("goal")]):
        stats = calculate_bmr_tdee(
            profile["age"], profile["gender"], profile["height"],
            float(profile["weight"]), profile.get("activity_level", 2), profile["goal"]
        )
        await update_profile(user["id"], stats)
        nutrition_text = (f"\n\n📊 Твои нормы:\n🔥 {stats['daily_calories']} ккал/день\n"
                          f"🥩 Б:{stats['daily_protein']}г / 🥑 Ж:{stats['daily_fat']}г / 🍞 У:{stats['daily_carbs']}г")
    supabase.table("users").update({"onboarding_done": True, "onboarding_step": "completed"}).eq("telegram_id", message.from_user.id).execute()
    goals = {'lose':'похудение 🔥','gain':'набор массы 💪','maintain':'поддержание ⚖️','health':'здоровье ❤️'}
    await message.answer(
        f"🎉 Всё записал!\n\nТвоя цель — {goals.get(profile.get('goal','health'),'твоя цель')}.{nutrition_text}\n\nЯ здесь чтобы помочь. Что начнём?",
        reply_markup=main_menu()
    )


@dp.callback_query(F.data.startswith("confirm_"))
async def on_confirm(callback: CallbackQuery):
    pid = int(callback.data.split("_")[1])
    res = supabase.table("pending_actions").select("*").eq("id", pid).execute()
    if not res.data:
        await callback.answer("Устарело")
        return
    action = res.data[0]
    user = await get_user(callback.from_user.id)
    if action["action_type"] == "weight":
        w = float(action["action_data"]["weight"])
        await update_profile(user["id"], {"weight": w})
        await save_checkin(user["id"], {"weight": w})
        await confirm_pending(pid)
        await callback.message.edit_text(f"✅ Вес {w} кг сохранён!")
    elif action["action_type"] == "workout_plan":
        await save_workout_plan(user["id"], action["action_data"]["plan"])
        await confirm_pending(pid)
        await callback.message.edit_text("✅ План сохранён!")


@dp.callback_query(F.data.startswith("cancel_"))
async def on_cancel(callback: CallbackQuery):
    pid = int(callback.data.split("_")[1])
    await cancel_pending(pid)
    await callback.message.edit_text("❌ Отменено")


@dp.callback_query(F.data.startswith("energy_"))
async def on_energy(callback: CallbackQuery):
    level = int(callback.data.split("_")[1])
    user = await get_user(callback.from_user.id)
    await save_checkin(user["id"], {"energy_level": level})
    sleep_h = await calculate_sleep(user["id"], callback.from_user.id)
    words = {1:"Понял, бережём силы.",3:"Хорошо!",5:"Огонь! 🔥"}
    msg = words.get(level,"Записал!")
    if sleep_h:
        msg += f"\n😴 Поспал {sleep_h} ч — {'маловато.' if sleep_h < 6 else 'хорошо!'}"
    if level <= 2:
        await callback.message.edit_text(msg)
        await callback.message.answer("Как насчёт тренировки?", reply_markup=workout_kb())
    else:
        await callback.message.edit_text(msg)


@dp.callback_query(F.data.startswith("workout_"))
async def on_workout(callback: CallbackQuery):
    choice = callback.data.split("_")[1]
    user = await get_user(callback.from_user.id)
    if choice == "skip":
        await save_checkin(user["id"], {"workout_done": False})
        await callback.message.edit_text("Окей, отдыхаем. Завтра наверстаем 💪")
    else:
        await save_checkin(user["id"], {"workout_done": True})
        await callback.message.edit_text(f"💪 Идёшь на {'лёгкую' if choice == 'light' else 'полную'} тренировку. Удачи!")


async def handle_workout(message: Message, user: dict):
    plan = await get_active_plan(user["id"])
    if plan:
        await message.answer(f"💪 Твой план:\n\n{plan['plan_text']}\n\nНапиши «новый план» для обновления.", reply_markup=main_menu())
    else:
        await message.answer("⏳ Составляю план...")
        profile = await get_profile(user["id"])
        plan_text = await generate_workout_plan(profile)
        pending = await create_pending(message.from_user.id, user["id"], "workout_plan", {"plan": plan_text}, "")
        if pending:
            await message.answer(f"📅 Вот твой план:\n\n{plan_text}\n\nСохраняем?", reply_markup=confirm_kb(pending["id"]))


async def handle_food_log(message: Message, user: dict, text: str, profile: dict, today: dict):
    await message.answer("⏳ Считаю КБЖУ...")
    nutrition = await calculate_nutrition(text)
    if not nutrition:
        await message.answer("Не смог посчитать. Опиши подробнее 🙏", reply_markup=main_menu())
        return
    await log_nutrition(user["id"], text, nutrition["calories"], nutrition["protein"], nutrition["fat"], nutrition["carbs"], nutrition.get("is_approximate", False))
    today_updated = await get_today_nutrition(user["id"])
    daily_cal = (profile or {}).get("daily_calories") or 2000
    daily_prot = (profile or {}).get("daily_protein") or 150
    remaining_cal = daily_cal - today_updated["calories"]
    approx = "~" if nutrition.get("is_approximate") else ""
    await message.answer(
        f"✅ {nutrition.get('description', text)}\n\n"
        f"🔥 {approx}{nutrition['calories']} ккал | 🥩 Б:{approx}{nutrition['protein']}г | 🥑 Ж:{approx}{nutrition['fat']}г | 🍞 У:{approx}{nutrition['carbs']}г\n\n"
        f"━━━━━━━━\n📈 За день: {round(today_updated['calories'])} / {round(daily_cal)} ккал\n"
        f"{'✅' if remaining_cal > 0 else '⚠️'} Осталось: {round(remaining_cal)} ккал | Белок: {round(daily_prot - today_updated['protein'])}г",
        reply_markup=main_menu()
    )


async def handle_progress(message: Message, user: dict):
    profile = await get_profile(user["id"]) or {}
    today = await get_today_nutrition(user["id"])
    checkin = await get_today_checkin(user["id"])
    daily_cal = profile.get("daily_calories") or 2000
    goals = {'lose':'похудение','gain':'набор','maintain':'поддержание','health':'здоровье'}
    sleep_str = f"{checkin.get('sleep_hours')} ч" if checkin and checkin.get('sleep_hours') else "не записан"
    energy_str = f"{checkin.get('energy_level')}/5" if checkin and checkin.get('energy_level') else "?"
    await message.answer(
        f"📊 {date.today().strftime('%d.%m.%Y')}\n\n"
        f"⚖️ Вес: {profile.get('weight','?')} кг | Цель: {goals.get(profile.get('goal'),'?')}\n"
        f"😴 Сон: {sleep_str} | ⚡ Энергия: {energy_str}\n\n"
        f"🍽 Питание:\n🔥 {round(today['calories'])} / {round(daily_cal)} ккал\n"
        f"🥩 Б:{round(today['protein'])}г | 🥑 Ж:{round(today['fat'])}г | 🍞 У:{round(today['carbs'])}г",
        reply_markup=main_menu()
    )


async def handle_schedule(message: Message, user: dict):
    schedule = await get_schedule(user["id"])
    if not schedule:
        await message.answer("📅 Расписание не настроено.\n\nРасскажи:\n• Во сколько просыпаешься?\n• Когда работаешь?\n• Когда удобно тренироваться?", reply_markup=main_menu())
    else:
        days_ru = {'mon':'Пн','tue':'Вт','wed':'Ср','thu':'Чт','fri':'Пт','sat':'Сб','sun':'Вс'}
        text = "📅 Расписание:\n\n"
        for s in schedule:
            day = days_ru.get(s['day_of_week'], s['day_of_week'])
            if s.get('is_rest_day'):
                text += f"{day}: 😴 Отдых\n"
            else:
                text += f"{day}: 🌅{s.get('wake_time','?')} | 💼{s.get('work_start','нет')} | 💪{s.get('workout_time','?')}\n"
        await message.answer(text, reply_markup=main_menu())


async def handle_profile(message: Message, user: dict):
    p = await get_profile(user["id"]) or {}
    goals = {'lose':'похудение','gain':'набор массы','maintain':'поддержание','health':'здоровье'}
    exp = {'beginner':'новичок','intermediate':'средний','advanced':'продвинутый'}
    await message.answer(
        f"⚙️ Профиль\n\n"
        f"📅 Возраст: {p.get('age','?')} | 📏 Рост: {p.get('height','?')} см | ⚖️ Вес: {p.get('weight','?')} кг\n"
        f"🎯 Цель: {goals.get(p.get('goal'),'?')} → {p.get('target_weight','?')} кг\n"
        f"💪 Опыт: {exp.get(p.get('experience'),'?')} | 🏋️ {p.get('equipment','?')} | {p.get('days_per_week','?')} дн/нед\n"
        f"🩺 Травмы: {', '.join(p.get('injuries') or []) or 'нет'}\n\n"
        f"🔥 {round(p.get('daily_calories') or 0)} ккал | Б:{round(p.get('daily_protein') or 0)} Ж:{round(p.get('daily_fat') or 0)} У:{round(p.get('daily_carbs') or 0)} г\n\n"
        f"/start — обновить данные",
        reply_markup=main_menu()
    )


@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    user = await get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin","superadmin"]: return
    stats = await get_stats()
    await message.answer(f"👑 Админ\n👥 {stats['total']} | ✅ {stats['active']} | 📋 {stats['onboarded']}\n\n/ban [id] | /broadcast [текст]")


@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    user = await get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin","superadmin"]: return
    args = message.text.split()
    if len(args) < 2: await message.answer("/ban [id]"); return
    await ban_user(int(args[1]))
    await message.answer(f"✅ Забанен {args[1]}")


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    user = await get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin","superadmin"]: return
    text = message.text.replace("/broadcast","").strip()
    if not text: await message.answer("/broadcast [текст]"); return
    users = await get_all_users("active")
    sent = 0
    for u in users:
        try:
            await bot.send_message(u["telegram_id"], text)
            sent += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Отправлено: {sent}/{len(users)}")


async def main():
    print("🤖 FitBot v2 запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

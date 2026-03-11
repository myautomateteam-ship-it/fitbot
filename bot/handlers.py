import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from database.db import (
    get_user, create_user, update_user, get_profile, update_profile,
    log_nutrition, get_today_nutrition, save_workout_plan, get_active_plan,
    get_stats, ban_user, unban_user, get_all_users
)
from bot.ai_service import (
    chat, generate_workout_plan, calculate_nutrition,
    process_onboarding_answer, calculate_bmr_tdee
)

load_dotenv(dotenv_path="config/.env")

bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
dp = Dispatcher(storage=MemoryStorage())

# Вопросы онбординга
ONBOARDING_QUESTIONS = {
    "ask_age":          "👋 Привет! Я Макс — твой личный фитнес-тренер.\n\nДавай познакомимся! Сколько тебе лет?",
    "ask_gender":       "Ты парень или девушка?",
    "ask_height":       "📏 Рост? (в сантиметрах, например: 178)",
    "ask_weight":       "⚖️ Вес? (в килограммах, например: 75)",
    "ask_goal":         "🎯 Какая главная цель?\n\n🔥 Похудеть\n💪 Набрать массу\n⚖️ Поддержать форму\n❤️ Улучшить здоровье",
    "ask_activity":     "🏃 Как ты сейчас двигаешься?\n\n1️⃣ Почти не хожу пешком\n2️⃣ Лёгкая активность\n3️⃣ Тренируюсь 3-5 раз в неделю\n4️⃣ Активен каждый день",
    "ask_experience":   "💪 Опыт тренировок?\n\n🌱 Новичок — никогда серьёзно не занимался\n📈 Средний — есть опыт в зале\n🚀 Продвинутый — тренируюсь давно",
    "ask_restrictions": "🩺 Есть травмы или ограничения по здоровью?\n(или напиши «нет»)",
    "ask_equipment":    "🏠 Где будешь тренироваться?\n\n🏠 Дома\n🏋️ В зале\n🔄 И там и там",
    "ask_workout_pref": "💭 Есть предпочтения в тренировках?\n(например: «люблю кардио», или «нет»)",
    "ask_diet":         "🥗 Особенности питания?\n(аллергии, вегетарианство, или «нет»)",
}

ONBOARDING_ORDER = list(ONBOARDING_QUESTIONS.keys())

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💪 Тренировка"), KeyboardButton(text="🥗 Питание")],
            [KeyboardButton(text="📊 Мой прогресс"), KeyboardButton(text="⚙️ Профиль")],
            [KeyboardButton(text="❓ Спросить тренера")]
        ],
        resize_keyboard=True
    )


# =============================================
# START
# =============================================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    telegram_id = message.from_user.id
    user = await get_user(telegram_id)
    
    if not user:
        # Новый пользователь — регистрируем
        user = await create_user(
            telegram_id=telegram_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
        # Ставим первый шаг онбординга
        await update_user(telegram_id, {"onboarding_done": False})
        await message.answer(
            ONBOARDING_QUESTIONS["ask_age"],
            reply_markup=ReplyKeyboardRemove()
        )
    elif not user.get("onboarding_done"):
        # Онбординг не завершён — продолжаем
        profile = await get_profile(user["id"])
        current_step = get_current_onboarding_step(profile)
        await message.answer(
            f"Продолжим знакомство! 😊\n\n{ONBOARDING_QUESTIONS.get(current_step, 'Введи данные:')}",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        # Уже зарегистрирован
        await message.answer(
            f"С возвращением, {message.from_user.first_name}! 💪\n\nЧем займёмся сегодня?",
            reply_markup=main_menu()
        )


def get_current_onboarding_step(profile: dict) -> str:
    """Определяем на каком шаге онбординга юзер"""
    field_to_step = {
        "age": "ask_age",
        "gender": "ask_gender",
        "height": "ask_height",
        "weight": "ask_weight",
        "goal": "ask_goal",
        "activity_level": "ask_activity",
        "experience": "ask_experience",
        "health_restrictions": "ask_restrictions",
        "equipment": "ask_equipment",
        "workout_preferences": "ask_workout_pref",
        "diet_preferences": "ask_diet",
    }
    
    if not profile:
        return "ask_age"
    
    for field, step in field_to_step.items():
        if not profile.get(field):
            return step
    
    return "completed"


# =============================================
# ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ
# =============================================

@dp.message(F.text)
async def handle_message(message: Message):
    telegram_id = message.from_user.id
    text = message.text.strip()
    
    # Получаем юзера
    user = await get_user(telegram_id)
    
    if not user:
        await cmd_start(message)
        return
    
    # Проверка бана
    if user.get("status") == "banned":
        await message.answer("🚫 Ваш аккаунт заблокирован.")
        return
    
    # Обновляем last_active
    from datetime import datetime
    await update_user(telegram_id, {"last_active": datetime.utcnow().isoformat()})
    
    # Проверяем онбординг
    if not user.get("onboarding_done"):
        await handle_onboarding(message, user, text)
        return
    
    # Команды меню
    if text == "💪 Тренировка":
        await handle_workout(message, user)
    elif text == "🥗 Питание":
        await handle_nutrition_menu(message)
    elif text == "📊 Мой прогресс":
        await handle_progress(message, user)
    elif text == "⚙️ Профиль":
        await handle_profile(message, user)
    elif text == "❓ Спросить тренера":
        await message.answer("Задай любой вопрос — отвечу! 💬", reply_markup=main_menu())
    else:
        # Проверяем — трекинг питания или просто чат
        nutrition_keywords = ["съел", "съела", "выпил", "выпила", "поел", "поела", "перекус", "завтрак", "обед", "ужин"]
        
        if any(kw in text.lower() for kw in nutrition_keywords):
            await handle_food_log(message, user, text)
        else:
            # AI чат
            profile = await get_profile(user["id"])
            await message.answer("⏳ Думаю...")
            reply = await chat(user["id"], text, profile)
            await message.answer(reply, reply_markup=main_menu())


# =============================================
# ОНБОРДИНГ
# =============================================

async def handle_onboarding(message: Message, user: dict, text: str):
    profile = await get_profile(user["id"])
    current_step = get_current_onboarding_step(profile)
    
    if current_step == "completed":
        await finish_onboarding(message, user, profile)
        return
    
    # AI обрабатывает ответ
    result = await process_onboarding_answer(current_step, text)
    
    if not result.get("valid"):
        await message.answer(result.get("reply", "Попробуй ещё раз 😊"))
        return
    
    # Сохраняем поле
    field = result["field"]
    value = result["value"]
    
    # Конвертация типов
    if field in ["age", "height", "activity_level"]:
        try:
            value = int(float(value))
        except:
            pass
    elif field == "weight":
        try:
            value = float(value)
        except:
            pass
    
    await update_profile(user["id"], {field: value})
    
    # Определяем следующий шаг
    next_step = result.get("next_state")
    
    if next_step == "completed":
        # Обновляем профиль после получения всех данных
        updated_profile = await get_profile(user["id"])
        await finish_onboarding(message, user, updated_profile)
    else:
        next_q = ONBOARDING_QUESTIONS.get(next_step, "")
        await message.answer(f"✅ Записал!\n\n{next_q}")


async def finish_onboarding(message: Message, user: dict, profile: dict):
    """Завершение анкеты — расчёт КБЖУ и приветствие"""
    
    # Рассчитываем BMR/TDEE если есть все данные
    if all([profile.get("age"), profile.get("gender"), profile.get("height"),
            profile.get("weight"), profile.get("activity_level"), profile.get("goal")]):
        
        stats = calculate_bmr_tdee(
            age=profile["age"],
            gender=profile["gender"],
            height=profile["height"],
            weight=float(profile["weight"]),
            activity_level=profile["activity_level"],
            goal=profile["goal"]
        )
        await update_profile(user["id"], stats)
        
        calories = stats["daily_calories"]
        protein = stats["daily_protein"]
        fat = stats["daily_fat"]
        carbs = stats["daily_carbs"]
        
        nutrition_text = f"\n\n📊 Твои нормы:\n🔥 {calories} ккал/день\n🥩 Белки: {protein}г\n🥑 Жиры: {fat}г\n🍞 Углеводы: {carbs}г"
    else:
        nutrition_text = ""
    
    # Помечаем онбординг завершённым
    await update_user(user["id"] if isinstance(user.get("id"), int) else message.from_user.id,
                      {"onboarding_done": True})
    # Обновляем по telegram_id
    from database.db import supabase
    supabase.table("users").update({"onboarding_done": True}).eq("telegram_id", message.from_user.id).execute()
    
    goal_text = {
        "lose": "похудение 🔥",
        "gain": "набор массы 💪",
        "maintain": "поддержание формы ⚖️",
        "health": "улучшение здоровья ❤️"
    }.get(profile.get("goal"), "твою цель")
    
    await message.answer(
        f"🎉 Отлично! Анкета заполнена!\n\n"
        f"Я запомнил всё о тебе и готов помочь достичь цели — {goal_text}."
        f"{nutrition_text}\n\n"
        f"Что делаем первым? 👇",
        reply_markup=main_menu()
    )


# =============================================
# ТРЕНИРОВКИ
# =============================================

async def handle_workout(message: Message, user: dict):
    plan = await get_active_plan(user["id"])
    
    if plan:
        await message.answer(
            f"💪 Твой текущий план:\n\n{plan['plan_text']}\n\n"
            f"Написать «новый план» чтобы сгенерировать новый.",
            reply_markup=main_menu()
        )
    else:
        await message.answer("⏳ Генерирую персональный план тренировок...")
        profile = await get_profile(user["id"])
        
        if not profile or not profile.get("goal"):
            await message.answer("Сначала заполни анкету! Напиши /start", reply_markup=main_menu())
            return
        
        plan_text = await generate_workout_plan(profile)
        await save_workout_plan(user["id"], plan_text)
        await message.answer(plan_text, reply_markup=main_menu())


# =============================================
# ПИТАНИЕ
# =============================================

async def handle_nutrition_menu(message: Message):
    await message.answer(
        "🥗 Трекинг питания\n\n"
        "Просто напиши что ты съел, например:\n"
        "• «съел 3 яйца и тост»\n"
        "• «выпил протеин 30г»\n"
        "• «обед: борщ и хлеб»\n\n"
        "Я посчитаю КБЖУ и скажу сколько осталось до нормы 👇",
        reply_markup=main_menu()
    )


async def handle_food_log(message: Message, user: dict, text: str):
    await message.answer("⏳ Считаю КБЖУ...")
    
    nutrition = await calculate_nutrition(text)
    
    if not nutrition:
        await message.answer("Не смог посчитать. Опиши еду подробнее 🙏", reply_markup=main_menu())
        return
    
    # Сохраняем в лог
    await log_nutrition(
        user_id=user["id"],
        food=text,
        calories=nutrition["calories"],
        protein=nutrition["protein"],
        fat=nutrition["fat"],
        carbs=nutrition["carbs"]
    )
    
    # Считаем остаток за день
    today = await get_today_nutrition(user["id"])
    profile = await get_profile(user["id"])
    
    daily_cal = profile.get("daily_calories") or 2000
    daily_prot = profile.get("daily_protein") or 150
    daily_fat = profile.get("daily_fat") or 60
    daily_carbs = profile.get("daily_carbs") or 200
    
    remaining_cal = daily_cal - today["calories"]
    remaining_prot = daily_prot - today["protein"]
    
    await message.answer(
        f"✅ {nutrition.get('description', text)}\n\n"
        f"📊 Добавлено:\n"
        f"🔥 {nutrition['calories']} ккал\n"
        f"🥩 Белки: {nutrition['protein']}г\n"
        f"🥑 Жиры: {nutrition['fat']}г\n"
        f"🍞 Углеводы: {nutrition['carbs']}г\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"📈 За сегодня: {round(today['calories'])} / {round(daily_cal)} ккал\n"
        f"{'✅' if remaining_cal > 0 else '⚠️'} Осталось: {round(remaining_cal)} ккал · {round(remaining_prot)}г белка",
        reply_markup=main_menu()
    )


# =============================================
# ПРОГРЕСС
# =============================================

async def handle_progress(message: Message, user: dict):
    profile = await get_profile(user["id"])
    today = await get_today_nutrition(user["id"])
    
    daily_cal = profile.get("daily_calories") or 2000
    
    await message.answer(
        f"📊 Твой прогресс сегодня\n\n"
        f"⚖️ Вес: {profile.get('weight', '?')} кг\n"
        f"🎯 Цель: {goals_map.get(profile.get('goal'), '?')}\n\n"
        f"🍽 Питание сегодня:\n"
        f"🔥 {round(today['calories'])} / {round(daily_cal)} ккал\n"
        f"🥩 Белки: {round(today['protein'])}г\n"
        f"🥑 Жиры: {round(today['fat'])}г\n"
        f"🍞 Углеводы: {round(today['carbs'])}г",
        reply_markup=main_menu()
    )


# =============================================
# ПРОФИЛЬ
# =============================================

async def handle_profile(message: Message, user: dict):
    profile = await get_profile(user["id"])
    
    goals = {'lose': 'похудение', 'gain': 'набор массы', 'maintain': 'поддержание', 'health': 'здоровье'}
    exp = {'beginner': 'новичок', 'intermediate': 'средний', 'advanced': 'продвинутый'}
    await message.answer(
        f"⚙️ Твой профиль\n\n"
        f"👤 {user.get('first_name', '')} {user.get('last_name', '') or ''}\n"
        f"📅 Возраст: {profile.get('age', '?')} лет\n"
        f"📏 Рост: {profile.get('height', '?')} см\n"
        f"⚖️ Вес: {profile.get('weight', '?')} кг\n"
        f"🎯 Цель: {goals.get(profile.get('goal'), '?')}\n"
        f"💪 Опыт: {exp.get(profile.get('experience'), '?')}\n"
        f"🏋️ Оборудование: {profile.get('equipment', '?')}\n\n"
        f"🔥 Норма: {round(profile.get('daily_calories') or 0)} ккал/день\n\n"
        f"Чтобы обновить данные — напиши /start",
        reply_markup=main_menu()
    )


# =============================================
# ADMIN КОМАНДЫ
# =============================================

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    user = await get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin", "superadmin"]:
        return
    
    stats = await get_stats()
    await message.answer(
        f"👑 Админ панель\n\n"
        f"👥 Всего юзеров: {stats['total']}\n"
        f"✅ Активных: {stats['active']}\n"
        f"🚫 Забанено: {stats['banned']}\n"
        f"📋 Заполнили анкету: {stats['onboarded']}\n\n"
        f"Команды:\n"
        f"/ban [telegram_id] — забанить\n"
        f"/unban [telegram_id] — разбанить\n"
        f"/broadcast [текст] — рассылка всем"
    )


@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    user = await get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin", "superadmin"]:
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /ban [telegram_id]")
        return
    
    await ban_user(int(args[1]))
    await message.answer(f"✅ Пользователь {args[1]} заблокирован")


@dp.message(Command("unban"))
async def cmd_unban(message: Message):
    user = await get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin", "superadmin"]:
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /unban [telegram_id]")
        return
    
    await unban_user(int(args[1]))
    await message.answer(f"✅ Пользователь {args[1]} разблокирован")


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    user = await get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin", "superadmin"]:
        return
    
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("Использование: /broadcast [текст сообщения]")
        return
    
    users = await get_all_users(status="active")
    sent = 0
    failed = 0
    
    await message.answer(f"📤 Начинаю рассылку для {len(users)} юзеров...")
    
    for u in users:
        try:
            await bot.send_message(u["telegram_id"], text)
            sent += 1
            await asyncio.sleep(0.05)  # rate limit
        except:
            failed += 1
    
    await message.answer(f"✅ Рассылка завершена!\nОтправлено: {sent}\nОшибок: {failed}")


# =============================================
# ЗАПУСК
# =============================================

async def main():
    print("🤖 FitBot запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

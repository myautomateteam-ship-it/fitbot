import asyncio
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import CommandStart

from bot.db import (
    get_user, create_user, update_user, get_profile, update_profile,
    today_food, get_checkin, get_notes, save_note,
    save_reminder, calc_bmr, set_sleep, calc_sleep
)
from bot.services.ai import ai_main, ai_extract_profile, ai_extract_reminder
from bot.handlers.common import (
    main_menu, SLEEP_WORDS, FOOD_WORDS,
    PROFILE_FIELDS, convert_value
)

router = Router()

# Обязательные поля для базового онбординга
REQUIRED_FIELDS = ["goal", "age", "weight", "height", "equipment"]

# Вопросы онбординга — задаются через AI но с этими подсказками
ONBOARDING_PROMPTS = {
    "goal": "спроси какая у юзера главная цель (похудение/набор/поддержание/здоровье)",
    "age": "спроси сколько лет юзеру",
    "weight": "спроси вес и рост юзера (оба параметра в одном вопросе)",
    "equipment": "спроси где тренируется — дома, в зале или оба варианта",
}


def get_missing_required(profile: dict) -> str | None:
    """Возвращает первое незаполненное обязательное поле"""
    p = profile or {}
    for field in REQUIRED_FIELDS:
        if not p.get(field):
            return field
    return None


def onboarding_complete(profile: dict) -> bool:
    return get_missing_required(profile) is None


@router.message(CommandStart())
async def cmd_start(message: Message):
    tg = message.from_user
    user = get_user(tg.id)

    if not user:
        create_user(tg.id, tg.username, tg.first_name, tg.last_name)
        update_user(tg.id, {"onboarding_done": False})
        user = get_user(tg.id)
        uid = user["id"]

        # AI представляется и описывает возможности
        intro = await ai_main(
            uid,
            f"Привет! Меня зовут {tg.first_name}. Это мой первый раз здесь.",
            {}, {}, [],
            system_override="""Ты — Макс, персональный фитнес-тренер.
Это первое сообщение юзера. Сделай следующее:
1. Поздоровайся по имени тепло и живо
2. Кратко опиши что ты умеешь (тренировки, питание, напоминания, расписание, трекинг калорий)
3. Скажи что для персональных рекомендаций нужно узнать о нём несколько вещей
4. Задай первый вопрос: какая главная цель?
Пиши живо, без списков, как человек."""
        )
        await message.answer(intro, reply_markup=ReplyKeyboardRemove())

    elif user.get("status") == "banned":
        await message.answer("🚫 Аккаунт заблокирован.")

    elif not user.get("onboarding_done"):
        profile = get_profile(user["id"])
        missing = get_missing_required(profile)
        if missing:
            reply = await ai_main(
                user["id"],
                "продолжи сбор данных",
                profile, {}, [],
                system_override=f"""Ты — Макс, тренер. Продолжаешь знакомство с юзером.
Нужно узнать: {ONBOARDING_PROMPTS.get(missing, 'следующий вопрос')}.
Задай вопрос естественно, в одно предложение."""
            )
            await message.answer(reply, reply_markup=ReplyKeyboardRemove())
        else:
            await finish_onboarding(message, user)
    else:
        await message.answer(
            f"С возвращением, {tg.first_name}! 💪 Чем займёмся?",
            reply_markup=main_menu()
        )


async def handle_ai_message(message: Message, user: dict, text: str):
    uid   = user["id"]
    tg_id = message.from_user.id
    profile = get_profile(uid)
    tz      = (profile or {}).get("timezone_offset") or 3
    today   = {**today_food(uid), **(get_checkin(uid) or {})}
    notes   = get_notes(uid)

    # Проверяем онбординг
    if not user.get("onboarding_done"):
        missing = get_missing_required(profile)
        if missing:
            await handle_onboarding_step(message, user, text, profile, missing)
            return

    # Параллельно: ответ + извлечение данных
    reply_task   = asyncio.create_task(ai_main(uid, text, profile, today, notes, tz))
    profile_task = asyncio.create_task(ai_extract_profile(text))
    remind_task  = asyncio.create_task(ai_extract_reminder(text, tz))

    reply, prof_data, reminders = await asyncio.gather(
        reply_task, profile_task, remind_task
    )

    # Сохраняем данные профиля
    if prof_data and isinstance(prof_data, dict):
        field = prof_data.get("field")
        value = prof_data.get("value")
        if field and field in PROFILE_FIELDS:
            converted = convert_value(field, value)
            if converted is not None:
                update_profile(uid, {field: converted})
                _try_calc_bmr(uid)
                print(f"✅ Profile: {field}={converted}")

    # Сохраняем напоминания
    for rem in (reminders or []):
        if not rem or not rem.get("time_utc"):
            continue
        days = rem.get("days") or []
        if not days:
            cur_day = ["mon","tue","wed","thu","fri","sat","sun"][datetime.utcnow().weekday()]
            days = [cur_day] if rem.get("one_time") else ["mon","tue","wed","thu","fri","sat","sun"]
        save_reminder(
            uid, tg_id, "custom",
            rem["time_utc"], days,
            rem.get("message", "Напоминание!"),
            one_time=rem.get("one_time", True)
        )
        print(f"✅ Reminder: {rem['time_utc']} msg={rem.get('message')}")

    has_menu = user.get("onboarding_done")
    await message.answer(reply, reply_markup=main_menu() if has_menu else ReplyKeyboardRemove())


async def handle_onboarding_step(message: Message, user: dict, text: str, profile: dict, missing_field: str):
    """Обрабатываем ответ юзера во время онбординга"""
    uid   = user["id"]
    tg_id = message.from_user.id

    # Параллельно извлекаем данные профиля И напоминания
    prof_data, reminders = await asyncio.gather(
        ai_extract_profile(text),
        ai_extract_reminder(text, (get_profile(uid) or {}).get("timezone_offset") or 3)
    )

    # Сохраняем напоминания даже во время онбординга
    for rem in (reminders or []):
        if not rem or not rem.get("time_utc"):
            continue
        days = rem.get("days") or []
        if not days:
            cur_day = ["mon","tue","wed","thu","fri","sat","sun"][datetime.utcnow().weekday()]
            days = [cur_day] if rem.get("one_time") else ["mon","tue","wed","thu","fri","sat","sun"]
        save_reminder(
            uid, tg_id, "custom",
            rem["time_utc"], days,
            rem.get("message", "Напоминание!"),
            one_time=rem.get("one_time", True)
        )
        print(f"✅ Reminder saved: {rem['time_utc']} msg={rem.get('message')}")

    saved = False
    if prof_data and isinstance(prof_data, dict):
        field = prof_data.get("field")
        value = prof_data.get("value")
        if field and field in PROFILE_FIELDS:
            converted = convert_value(field, value)
            if converted is not None:
                update_profile(uid, {field: converted})
                saved = True
                print(f"✅ Onboarding: {field}={converted}")

    # Обновляем профиль
    profile = get_profile(uid)
    missing = get_missing_required(profile)

    if missing is None:
        _try_calc_bmr(uid)
        await finish_onboarding(message, user)
    else:
        context = f"Юзер ответил: '{text}'. "
        if not saved:
            context += f"Ответ непонятен, переспроси мягко про {missing_field}. "
        else:
            context += f"Следующий вопрос: {ONBOARDING_PROMPTS.get(missing, 'узнай следующие данные')}. "

        reply = await ai_main(
            uid, text, profile, {}, [],
            system_override=f"""Ты — Макс, тренер. Собираешь данные юзера.
{context}
Задай вопрос коротко и живо. Один вопрос."""
        )
        await message.answer(reply, reply_markup=ReplyKeyboardRemove())


async def finish_onboarding(message: Message, user: dict):
    """Завершение онбординга — показываем меню и предлагаем дополнить"""
    uid = user["id"]
    profile = get_profile(uid) or {}
    tg_id = message.from_user.id

    _try_calc_bmr(uid)
    update_user(tg_id, {"onboarding_done": True})

    # Ставим базовые напоминания
    tz = profile.get("timezone_offset") or 3
    wake = profile.get("wake_time") or "08:00"
    if isinstance(wake, str):
        try:
            h, m = map(int, str(wake)[:5].split(":"))
            utc_h = (h - tz) % 24
            wake_utc = f"{utc_h:02d}:{m:02d}"
        except Exception:
            wake_utc = "05:00"
    else:
        wake_utc = "05:00"

    all_days = ["mon","tue","wed","thu","fri","sat","sun"]
    save_reminder(uid, tg_id, "morning", wake_utc, all_days, "", one_time=False)
    save_reminder(uid, tg_id, "evening", "18:00", all_days, "", one_time=False)

    goals = {'lose':'похудение 🔥','gain':'набор массы 💪','maintain':'поддержание ⚖️','health':'здоровье ❤️'}
    goal_text = goals.get(profile.get('goal',''), 'твою цель')

    cal = profile.get('daily_calories')
    nutrition_text = f"\n🔥 Твоя норма: {round(cal)} ккал/день" if cal else ""

    await message.answer(
        f"🎉 Отлично, база есть!\n\n"
        f"Твоя цель — {goal_text}.{nutrition_text}\n\n"
        f"Чем больше я знаю о тебе — тем точнее мои советы. "
        f"Можешь дополнить профиль прямо сейчас:\n\n"
        f"💬 Просто напиши мне про травмы, опыт тренировок, "
        f"особенности питания или расписание — запомню всё.\n\n"
        f"Или выбери что делаем 👇",
        reply_markup=main_menu()
    )


def _try_calc_bmr(uid: int):
    """Пересчитываем нормы если есть все данные"""
    p = get_profile(uid)
    if all([p.get("age"), p.get("gender"), p.get("height"), p.get("weight"), p.get("goal")]):
        stats = calc_bmr(
            p["age"], p["gender"], p["height"],
            float(p["weight"]), p.get("activity_level") or 2, p["goal"]
        )
        update_profile(uid, stats)


def _setup_default_reminders(uid, tg_id, profile):
    wake = (profile or {}).get("wake_time") or "08:00"
    if isinstance(wake, str):
        try:
            h, m = map(int, str(wake)[:5].split(":"))
            tz = (profile or {}).get("timezone_offset") or 3
            utc_h = (h - tz) % 24
            wake_utc = f"{utc_h:02d}:{m:02d}"
        except Exception:
            wake_utc = "05:00"
    else:
        wake_utc = "05:00"
    all_days = ["mon","tue","wed","thu","fri","sat","sun"]
    save_reminder(uid, tg_id, "morning", wake_utc, all_days, "", one_time=False)
    save_reminder(uid, tg_id, "evening", "18:00", all_days, "", one_time=False)

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


@router.message(CommandStart())
async def cmd_start(message: Message):
    tg = message.from_user
    user = get_user(tg.id)

    if not user:
        create_user(tg.id, tg.username, tg.first_name, tg.last_name)
        update_user(tg.id, {"onboarding_done": False})
        user = get_user(tg.id)
        uid = user["id"]
        reply = await ai_main(uid, f"Привет! Меня зовут {tg.first_name}", {}, {}, [], tz=3)
        await message.answer(reply, reply_markup=ReplyKeyboardRemove())
    elif user.get("status") == "banned":
        await message.answer("🚫 Аккаунт заблокирован.")
    else:
        await message.answer(f"С возвращением, {tg.first_name}! 💪", reply_markup=main_menu())


async def handle_ai_message(message: Message, user: dict, text: str):
    """Основной обработчик — AI чат + параллельное извлечение данных"""
    uid     = user["id"]
    tg_id   = message.from_user.id
    profile = get_profile(uid)
    tz      = (profile or {}).get("timezone_offset") or 3
    today   = {**today_food(uid), **(get_checkin(uid) or {})}
    notes   = get_notes(uid)

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
                # Пересчитываем нормы если достаточно данных
                p = get_profile(uid)
                if all([p.get("age"), p.get("gender"), p.get("height"),
                        p.get("weight"), p.get("goal")]):
                    stats = calc_bmr(
                        p["age"], p["gender"], p["height"],
                        float(p["weight"]), p.get("activity_level") or 2, p["goal"]
                    )
                    update_profile(uid, stats)
                    if not user.get("onboarding_done"):
                        update_user(tg_id, {"onboarding_done": True})
                        _setup_default_reminders(uid, tg_id, p)
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
        print(f"✅ Reminder: {rem['time_utc']} one_time={rem.get('one_time')} msg={rem.get('message')}")

    has_menu = user.get("onboarding_done") or bool((get_profile(uid) or {}).get("goal"))
    await message.answer(reply, reply_markup=main_menu() if has_menu else ReplyKeyboardRemove())


def _setup_default_reminders(uid, tg_id, profile):
    """Базовые напоминания после онбординга"""
    wake = (profile or {}).get("wake_time") or "08:00"
    if isinstance(wake, str):
        wake = wake[:5]
    all_days = ["mon","tue","wed","thu","fri","sat","sun"]
    tz = (profile or {}).get("timezone_offset") or 3
    # Переводим wake_time в UTC
    try:
        h, m = map(int, wake.split(":"))
        utc_h = (h - tz) % 24
        wake_utc = f"{utc_h:02d}:{m:02d}"
    except Exception:
        wake_utc = "05:00"

    save_reminder(uid, tg_id, "morning", wake_utc, all_days, "", one_time=False)
    save_reminder(uid, tg_id, "evening", "18:00", all_days, "", one_time=False)

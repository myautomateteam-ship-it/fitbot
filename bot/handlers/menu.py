from datetime import date
from aiogram import Router
from aiogram.types import Message

from bot.db import (
    get_profile, today_food, get_checkin, get_plan, save_plan
)
from bot.db.client import sb
from bot.services.ai import ai_plan
from bot.handlers.common import main_menu

router = Router()


async def handle_workout(message: Message, user: dict):
    uid = user["id"]
    plan = get_plan(uid)
    if plan:
        await message.answer(
            f"💪 Твой план:\n\n{plan['plan_text']}\n\n"
            f"Напиши «новый план» для обновления.",
            reply_markup=main_menu()
        )
    else:
        profile = get_profile(uid)
        if not profile or not profile.get("goal"):
            await message.answer(
                "Расскажи мне о своей цели — составлю план! 💪",
                reply_markup=main_menu()
            )
            return
        await message.answer("⏳ Составляю персональный план...")
        plan_text = await ai_plan(profile)
        save_plan(uid, plan_text)
        await message.answer(f"📅 {plan_text}", reply_markup=main_menu())


async def handle_progress(message: Message, user: dict):
    uid = user["id"]
    profile = get_profile(uid) or {}
    today   = today_food(uid)
    checkin = get_checkin(uid)
    dc = profile.get("daily_calories") or 2000
    goals = {'lose': 'похудение', 'gain': 'набор', 'maintain': 'поддержание', 'health': 'здоровье'}
    sleep_str  = f"{checkin.get('sleep_hours')} ч" if checkin and checkin.get('sleep_hours') else "не записан"
    energy_str = f"{checkin.get('energy_level')}/5" if checkin and checkin.get('energy_level') else "—"

    await message.answer(
        f"📊 {date.today().strftime('%d.%m.%Y')}\n\n"
        f"⚖️ {profile.get('weight', '?')} кг | "
        f"🎯 {goals.get(profile.get('goal'), '?')}\n"
        f"😴 Сон: {sleep_str} | ⚡ {energy_str}\n\n"
        f"🍽 Питание:\n"
        f"🔥 {round(today.get('calories', 0))} / {round(dc)} ккал\n"
        f"🥩 Б:{round(today.get('protein', 0))}г | "
        f"🥑 Ж:{round(today.get('fat', 0))}г | "
        f"🍞 У:{round(today.get('carbs', 0))}г",
        reply_markup=main_menu()
    )


async def handle_schedule(message: Message, user: dict):
    uid = user["id"]
    r = sb.table("schedule").select("*").eq("user_id", uid).execute()
    schedule = r.data or []

    if not schedule:
        await message.answer(
            "📅 Расписание не настроено.\n\n"
            "Расскажи:\n"
            "• Во сколько просыпаешься?\n"
            "• Когда работаешь?\n"
            "• Когда удобно тренироваться?\n\n"
            "Напиши — разберусь! 😊",
            reply_markup=main_menu()
        )
    else:
        days = {'mon': 'Пн', 'tue': 'Вт', 'wed': 'Ср', 'thu': 'Чт',
                'fri': 'Пт', 'sat': 'Сб', 'sun': 'Вс'}
        txt = "📅 Расписание:\n\n"
        for s in schedule:
            d = days.get(s['day_of_week'], s['day_of_week'])
            if s.get('is_rest_day'):
                txt += f"{d}: 😴 Отдых\n"
            else:
                work = f"{s.get('work_start','')}-{s.get('work_end','')}" if s.get('work_start') else "нет"
                txt += f"{d}: 🌅{s.get('wake_time','?')} | 💼{work} | 💪{s.get('workout_time','?')}\n"
        txt += "\nЧтобы изменить — просто напиши!"
        await message.answer(txt, reply_markup=main_menu())


async def handle_profile_view(message: Message, user: dict):
    uid = user["id"]
    p = get_profile(uid) or {}
    goals = {'lose': 'похудение', 'gain': 'набор', 'maintain': 'поддержание', 'health': 'здоровье'}
    exp   = {'beginner': 'новичок', 'intermediate': 'средний', 'advanced': 'продвинутый'}

    await message.answer(
        f"⚙️ Профиль\n\n"
        f"👤 {user.get('first_name', '')} | "
        f"{'♂️' if p.get('gender') == 'male' else '♀️' if p.get('gender') == 'female' else '?'} | "
        f"{p.get('age', '?')} лет\n"
        f"📏 {p.get('height', '?')} см | ⚖️ {p.get('weight', '?')} кг → 🎯 {p.get('target_weight', '?')} кг\n"
        f"🏆 {goals.get(p.get('goal'), '?')} | 💪 {exp.get(p.get('experience'), '?')}\n"
        f"🏋️ {p.get('equipment', '?')} | {p.get('days_per_week', '?')} дн/нед\n"
        f"🩺 {', '.join(p.get('injuries') or []) or 'нет'}\n\n"
        f"🔥 {round(p.get('daily_calories') or 0)} ккал/день\n"
        f"Б:{round(p.get('daily_protein') or 0)}г | "
        f"Ж:{round(p.get('daily_fat') or 0)}г | "
        f"У:{round(p.get('daily_carbs') or 0)}г",
        reply_markup=main_menu()
    )

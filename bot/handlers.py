import os
import asyncio
import json
import re
from datetime import datetime, date, timedelta
from openai import AsyncOpenAI
from aiogram import Bot, Dispatcher, F
from aiogram.types import (Message, CallbackQuery, ReplyKeyboardMarkup,
                           KeyboardButton, ReplyKeyboardRemove,
                           InlineKeyboardMarkup, InlineKeyboardButton)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv(dotenv_path="config/.env")

# =============================================
# ИНИЦИАЛИЗАЦИЯ
# =============================================

bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
dp = Dispatcher(storage=MemoryStorage())
openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o-mini"

supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)

# =============================================
# КЛАВИАТУРЫ
# =============================================

def main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💪 Тренировка"), KeyboardButton(text="🥗 Питание")],
        [KeyboardButton(text="📊 Прогресс"),   KeyboardButton(text="📅 Расписание")],
        [KeyboardButton(text="⚙️ Профиль"),    KeyboardButton(text="💬 Спросить Макса")]
    ], resize_keyboard=True)

def confirm_kb(pid):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да", callback_data=f"ok_{pid}"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"no_{pid}")
    ]])

def energy_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="😴 Устал", callback_data="nrg_1"),
        InlineKeyboardButton(text="😐 Норм",  callback_data="nrg_3"),
        InlineKeyboardButton(text="⚡ Огонь", callback_data="nrg_5"),
    ]])

def workout_adapt_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💪 Полную",   callback_data="wkt_full"),
        InlineKeyboardButton(text="⚡ Лёгкую",   callback_data="wkt_light"),
        InlineKeyboardButton(text="😴 Пропустить", callback_data="wkt_skip"),
    ]])

# =============================================
# БАЗА ДАННЫХ
# =============================================

def db_get_user(telegram_id):
    r = supabase.table("users").select("*").eq("telegram_id", telegram_id).execute()
    return r.data[0] if r.data else None

def db_create_user(telegram_id, username, first_name, last_name=None):
    r = supabase.table("users").insert({
        "telegram_id": telegram_id, "username": username,
        "first_name": first_name, "last_name": last_name
    }).execute()
    return r.data[0] if r.data else None

def db_update_user(telegram_id, data):
    data["last_active"] = datetime.utcnow().isoformat()
    supabase.table("users").update(data).eq("telegram_id", telegram_id).execute()

def db_get_profile(user_id):
    r = supabase.table("profile").select("*").eq("user_id", user_id).execute()
    return r.data[0] if r.data else None

def db_update_profile(user_id, data):
    data["updated_at"] = datetime.utcnow().isoformat()
    supabase.table("profile").update(data).eq("user_id", user_id).execute()

def db_save_message(user_id, role, content):
    supabase.table("messages").insert({
        "user_id": user_id, "role": role, "content": content
    }).execute()

def db_get_history(user_id, limit=15):
    r = supabase.table("messages").select("role,content")\
        .eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
    return list(reversed(r.data)) if r.data else []

def db_log_food(user_id, food, cal, prot, fat, carbs, approx=False):
    supabase.table("nutrition_log").insert({
        "user_id": user_id, "food_description": food,
        "calories": cal, "protein": prot, "fat": fat, "carbs": carbs,
        "is_approximate": approx
    }).execute()

def db_today_food(user_id):
    today = date.today().isoformat()
    r = supabase.table("nutrition_log").select("*")\
        .eq("user_id", user_id).gte("logged_at", f"{today}T00:00:00").execute()
    total = {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
    for item in (r.data or []):
        total["calories"] += item.get("calories") or 0
        total["protein"]  += item.get("protein") or 0
        total["fat"]      += item.get("fat") or 0
        total["carbs"]    += item.get("carbs") or 0
    return total

def db_save_plan(user_id, plan_text):
    supabase.table("workout_plans").update({"is_active": False}).eq("user_id", user_id).execute()
    supabase.table("workout_plans").insert({
        "user_id": user_id, "plan_text": plan_text,
        "week_start": date.today().isoformat(), "is_active": True
    }).execute()

def db_get_plan(user_id):
    r = supabase.table("workout_plans").select("*")\
        .eq("user_id", user_id).eq("is_active", True).execute()
    return r.data[0] if r.data else None

def db_save_checkin(user_id, data):
    today = date.today().isoformat()
    data["user_id"] = user_id
    data["date"] = today
    ex = supabase.table("daily_checkins").select("id")\
        .eq("user_id", user_id).eq("date", today).execute()
    if ex.data:
        supabase.table("daily_checkins").update(data)\
            .eq("user_id", user_id).eq("date", today).execute()
    else:
        supabase.table("daily_checkins").insert(data).execute()

def db_get_checkin(user_id):
    today = date.today().isoformat()
    r = supabase.table("daily_checkins").select("*")\
        .eq("user_id", user_id).eq("date", today).execute()
    return r.data[0] if r.data else None

def db_set_sleep(telegram_id):
    supabase.table("users").update({
        "sleep_time_last": datetime.utcnow().isoformat()
    }).eq("telegram_id", telegram_id).execute()

def db_calc_sleep(user_id, telegram_id):
    r = supabase.table("users").select("sleep_time_last")\
        .eq("telegram_id", telegram_id).execute()
    if not r.data or not r.data[0].get("sleep_time_last"):
        return None
    sleep_t = datetime.fromisoformat(r.data[0]["sleep_time_last"].replace("Z",""))
    hours = round((datetime.utcnow() - sleep_t).seconds / 3600, 1)
    if 2 <= hours <= 14:
        db_save_checkin(user_id, {"sleep_hours": hours})
        return hours
    return None

def db_save_note(user_id, category, key, value, source=None):
    ex = supabase.table("user_notes").select("id")\
        .eq("user_id", user_id).eq("key", key).execute()
    if ex.data:
        supabase.table("user_notes").update({
            "value": value, "source": source,
            "last_mentioned": datetime.utcnow().isoformat()
        }).eq("user_id", user_id).eq("key", key).execute()
    else:
        supabase.table("user_notes").insert({
            "user_id": user_id, "category": category,
            "key": key, "value": value, "source": source
        }).execute()

def db_get_notes(user_id):
    r = supabase.table("user_notes").select("*")\
        .eq("user_id", user_id).eq("is_active", True).execute()
    return r.data or []

def db_save_reminder(user_id, telegram_id, rtype, message, time_of_day, days, use_gpt=True):
    supabase.table("reminders").insert({
        "user_id": user_id, "telegram_id": telegram_id,
        "type": rtype, "message": message,
        "time_of_day": time_of_day, "days_of_week": days,
        "use_gpt": use_gpt, "is_active": True
    }).execute()

def db_get_due_reminders(current_time, day):
    r = supabase.table("reminders").select("*").eq("is_active", True).execute()
    due = []
    for rem in (r.data or []):
        t = (rem.get("time_of_day") or "")[:5]
        days = rem.get("days_of_week") or []
        if t == current_time and day in days:
            due.append(rem)
    return due

def db_save_schedule(user_id, day, data):
    data["user_id"] = user_id
    data["day_of_week"] = day
    ex = supabase.table("schedule").select("id")\
        .eq("user_id", user_id).eq("day_of_week", day).execute()
    if ex.data:
        supabase.table("schedule").update(data)\
            .eq("user_id", user_id).eq("day_of_week", day).execute()
    else:
        supabase.table("schedule").insert(data).execute()

def db_get_schedule(user_id):
    r = supabase.table("schedule").select("*").eq("user_id", user_id).execute()
    return r.data or []

def db_create_pending(telegram_id, user_id, atype, adata, preview):
    supabase.table("pending_actions").delete()\
        .eq("user_id", user_id).eq("status", "pending").execute()
    r = supabase.table("pending_actions").insert({
        "user_id": user_id, "telegram_id": telegram_id,
        "action_type": atype, "action_data": adata, "preview_text": preview
    }).execute()
    return r.data[0] if r.data else None

def db_get_pending(pid):
    r = supabase.table("pending_actions").select("*").eq("id", pid).execute()
    return r.data[0] if r.data else None

def db_confirm_pending(pid):
    supabase.table("pending_actions").update({"status": "confirmed"}).eq("id", pid).execute()

def db_cancel_pending(pid):
    supabase.table("pending_actions").update({"status": "cancelled"}).eq("id", pid).execute()

def db_get_stats():
    total = supabase.table("users").select("id", count="exact").execute()
    active = supabase.table("users").select("id", count="exact").eq("status","active").execute()
    done = supabase.table("users").select("id", count="exact").eq("onboarding_done",True).execute()
    return {"total": total.count or 0, "active": active.count or 0, "onboarded": done.count or 0}

def db_get_patterns(user_id):
    r = supabase.table("user_patterns").select("*").eq("user_id", user_id).execute()
    return r.data[0] if r.data else {}

def db_get_all_users(status="active"):
    r = supabase.table("users").select("*").eq("status", status).execute()
    return r.data or []

def db_ban(telegram_id):
    supabase.table("users").update({"status":"banned"}).eq("telegram_id", telegram_id).execute()

def db_unban(telegram_id):
    supabase.table("users").update({"status":"active"}).eq("telegram_id", telegram_id).execute()

# =============================================
# AI СЕРВИС
# =============================================

def build_context(profile, today, patterns, notes):
    p = profile or {}
    t = today or {}
    pat = patterns or {}
    goals = {'lose':'похудение','gain':'набор массы','maintain':'поддержание','health':'здоровье'}
    exp = {'beginner':'новичок','intermediate':'средний','advanced':'продвинутый'}

    ctx = f"""ДАННЫЕ ЮЗЕРА (только факты из базы):
Возраст: {p.get('age','?')} лет | Пол: {'м' if p.get('gender')=='male' else 'ж' if p.get('gender')=='female' else '?'}
Рост: {p.get('height','?')} см | Вес: {p.get('weight','?')} кг | Цель: {goals.get(p.get('goal'),'?')}
Опыт: {exp.get(p.get('experience'),'?')} | Оборудование: {p.get('equipment','?')} | Дней/нед: {p.get('days_per_week','?')}
Травмы: {', '.join(p.get('injuries') or []) or 'нет'}
Питание: {p.get('diet_type','стандарт')} | Аллергии: {', '.join(p.get('food_allergies') or []) or 'нет'}
Норма: {p.get('daily_calories','?')} ккал | Б:{p.get('daily_protein','?')}г Ж:{p.get('daily_fat','?')}г У:{p.get('daily_carbs','?')}г

СЕГОДНЯ:
Съедено: {round(t.get('calories',0))} / {round(p.get('daily_calories') or 2000)} ккал
Белок: {round(t.get('protein',0))}г | Стрик: {pat.get('streak_current',0)} дней"""

    checkin = t.get('energy_level') or t.get('sleep_hours')
    if checkin:
        ctx += f"\nЭнергия: {t.get('energy_level','?')}/5 | Сон: {t.get('sleep_hours','?')} ч"

    if notes:
        ctx += "\n\nЗАМЕТКИ О ЮЗЕРЕ:\n" + "\n".join([f"• {n['value']}" for n in notes[:8]])

    return ctx


def system_prompt(profile, today, patterns, notes):
    style = (profile or {}).get('communication_style', 'friendly')
    tones = {'friendly':'тепло и дружелюбно','strict':'чётко и по делу','humor':'с юмором и легко'}
    tone = tones.get(style, 'тепло и дружелюбно')
    ctx = build_context(profile, today, patterns, notes)
    return f"""Ты — Макс, персональный фитнес-тренер и коуч. Общаешься {tone}.
Только русский язык. Максимум 200 слов. Используй эмодзи умеренно.

ЖЁСТКИЕ ПРАВИЛА:
• Используй ТОЛЬКО данные из контекста — никогда не придумывай цифры
• Неточные калории — добавляй "~" перед числом
• Медицина, диагнозы, лекарства — всегда "обратись к врачу"
• Травмы юзера — НИКОГДА не предлагай запрещённые упражнения
• Не обещай конкретные результаты ("похудеешь на 5кг")

{ctx}"""


async def ai_chat(user_id, message, profile=None, today=None, patterns=None, notes=None):
    db_save_message(user_id, "user", message)
    history = db_get_history(user_id)
    msgs = [{"role":"system","content":system_prompt(profile,today,patterns,notes)}]
    msgs += [{"role":m["role"],"content":m["content"]} for m in history]
    r = await openai.chat.completions.create(model=MODEL, messages=msgs, max_tokens=500, temperature=0.8)
    reply = r.choices[0].message.content
    db_save_message(user_id, "assistant", reply)
    return reply


async def ai_extract(text):
    prompt = f"""Сообщение: "{text}"
Извлеки данные. Только JSON без лишнего текста:
{{"weight":число или null,"sleep_going":true если идёт спать иначе false,"food_log":true если описывает еду иначе false,"preference":"предпочтение или null","note":"важная инфо или null"}}"""
    try:
        r = await openai.chat.completions.create(
            model=MODEL, messages=[{"role":"user","content":prompt}],
            max_tokens=150, temperature=0.1
        )
        m = re.search(r'\{[\s\S]*\}', r.choices[0].message.content)
        if m: return json.loads(m.group(0))
    except: pass
    return {}


async def ai_kbju(food):
    prompt = f"""КБЖУ для: "{food}". Только JSON:
{{"calories":число,"protein":число,"fat":число,"carbs":число,"description":"что посчитал","is_approximate":true или false}}"""
    try:
        r = await openai.chat.completions.create(
            model=MODEL,
            messages=[{"role":"system","content":"Ты диетолог. Только JSON."},
                      {"role":"user","content":prompt}],
            max_tokens=150, temperature=0.1
        )
        m = re.search(r'\{[\s\S]*\}', r.choices[0].message.content)
        if m: return json.loads(m.group(0))
    except: pass
    return None


async def ai_workout_plan(profile):
    injuries = ', '.join(profile.get('injuries') or []) or 'нет'
    r = await openai.chat.completions.create(
        model=MODEL,
        messages=[
            {"role":"system","content":"Ты опытный тренер. Составляй реалистичные планы. Учитывай травмы — это критично для безопасности."},
            {"role":"user","content":f"""Составь план тренировок на неделю:
Цель: {profile.get('goal')} | Опыт: {profile.get('experience')}
Дней: {profile.get('days_per_week',3)} | По {profile.get('session_duration',60)} мин
Оборудование: {profile.get('equipment')} | Травмы (ИСКЛЮЧИТЬ): {injuries}

Формат:
📅 ПЛАН НА НЕДЕЛЮ

День 1 — [название]:
• Упражнение — подходы×повторения
...

Дни отдыха: [дни]
💡 Главный совет: [1 предложение под цель]"""}
        ],
        max_tokens=900, temperature=0.5
    )
    return r.choices[0].message.content


async def ai_onboarding(step, answer):
    fields = {
        "ask_age":      ("age",              "число 10-100"),
        "ask_gender":   ("gender",           "male или female по смыслу"),
        "ask_height":   ("height",           "число 140-220"),
        "ask_weight":   ("weight",           "число 30-200"),
        "ask_target":   ("target_weight",    "число или null если не знает"),
        "ask_goal":     ("goal",             "lose/gain/maintain/health по смыслу"),
        "ask_exp":      ("experience",       "beginner/intermediate/advanced по смыслу"),
        "ask_days":     ("days_per_week",    "число 1-7"),
        "ask_duration": ("session_duration", "число минут 20-180"),
        "ask_equip":    ("equipment",        "home/gym/both по смыслу"),
        "ask_wake":     ("wake_time",        "время HH:MM"),
        "ask_work":     ("work_type",        "sitting/active/mixed/none"),
        "ask_travel":   ("travel_time_gym",  "число минут или 0 если дома"),
        "ask_injuries": ("injuries",         "массив строк или []"),
        "ask_diet":     ("diet_type",        "standard/vegetarian/vegan/keto/other"),
        "ask_allergy":  ("food_allergies",   "массив строк или []"),
        "ask_style":    ("communication_style", "friendly/strict/humor по смыслу"),
    }
    nexts = {
        "ask_age":"ask_gender","ask_gender":"ask_height","ask_height":"ask_weight",
        "ask_weight":"ask_target","ask_target":"ask_goal","ask_goal":"ask_exp",
        "ask_exp":"ask_days","ask_days":"ask_duration","ask_duration":"ask_equip",
        "ask_equip":"ask_wake","ask_wake":"ask_work","ask_work":"ask_travel",
        "ask_travel":"ask_injuries","ask_injuries":"ask_diet","ask_diet":"ask_allergy",
        "ask_allergy":"ask_style","ask_style":"completed"
    }
    field, rule = fields.get(step, ("x","любой текст"))
    nxt = nexts.get(step, "completed")
    try:
        r = await openai.chat.completions.create(
            model=MODEL,
            messages=[{"role":"user","content":
                f'Шаг: {step}, поле: {field}, правило: {rule}\nОтвет: "{answer}"\n'
                f'Валидно: {{"valid":true,"field":"{field}","value":"...","next":"{nxt}"}}\n'
                f'Невалидно: {{"valid":false,"reply":"короткое объяснение"}}\nТолько JSON.'}],
            max_tokens=100, temperature=0.1
        )
        m = re.search(r'\{[\s\S]*\}', r.choices[0].message.content)
        if m: return json.loads(m.group(0))
    except: pass
    return {"valid": False, "reply": "Не понял, попробуй ещё раз 😊"}


async def ai_reminder(rtype, profile, today, patterns, notes):
    ctx = build_context(profile, today, patterns, notes)
    texts = {
        "morning": "Доброе утро! Напиши план на день и мотивацию. 2-3 живых предложения.",
        "workout": "Напомни о тренировке. Учти самочувствие. 1-2 предложения.",
        "evening": "Вечерний итог дня. Что хорошо, что улучшить, что завтра. 3-4 предложения.",
        "water":   "Напомни выпить воду. Коротко с юмором. 1 предложение.",
        "sleep":   "Пора готовиться ко сну. Мягко. 1 предложение.",
    }
    r = await openai.chat.completions.create(
        model=MODEL,
        messages=[{"role":"system","content":f"Ты тренер Макс. {ctx}"},
                  {"role":"user","content":texts.get(rtype,"Короткое мотивирующее.")}],
        max_tokens=150, temperature=0.9
    )
    return r.choices[0].message.content


def calc_bmr_tdee(age, gender, height, weight, activity, goal):
    bmr = (10*weight + 6.25*height - 5*age + (5 if gender=="male" else -161))
    tdee = bmr * {1:1.2,2:1.375,3:1.55,4:1.725}.get(activity,1.375)
    cal = tdee + {'lose':-400,'gain':300}.get(goal,0)
    prot = weight * 2.0
    fat = cal * 0.25 / 9
    carbs = (cal - prot*4 - fat*9) / 4
    return {"bmr":round(bmr,1),"tdee":round(tdee,1),"daily_calories":round(cal,1),
            "daily_protein":round(prot,1),"daily_fat":round(fat,1),"daily_carbs":round(carbs,1)}

# =============================================
# ОНБОРДИНГ — вопросы
# =============================================

OB_QUESTIONS = {
    "ask_age":      "Сколько тебе лет?",
    "ask_gender":   "Ты парень или девушка?",
    "ask_height":   "📏 Рост в сантиметрах?",
    "ask_weight":   "⚖️ Вес сейчас в кг?",
    "ask_target":   "🎯 Целевой вес? (или «не знаю»)",
    "ask_goal":     "Какая цель?\n\n🔥 Похудеть\n💪 Набрать массу\n⚖️ Поддержать форму\n❤️ Здоровье",
    "ask_exp":      "Опыт тренировок?\n\n🌱 Новичок\n📈 Средний\n🚀 Продвинутый",
    "ask_days":     "Сколько дней в неделю тренируешься?",
    "ask_duration": "Сколько минут на тренировку? (например: 60)",
    "ask_equip":    "Где тренируешься?\n\n🏠 Дома\n🏋️ В зале\n🔄 И там и там",
    "ask_wake":     "⏰ Во сколько просыпаешься? (например: 08:00)",
    "ask_work":     "Работа — сидячая, активная или смешанная?\n(или «нет работы»)",
    "ask_travel":   "🚶 Сколько минут до зала? (если дома — напиши 0)",
    "ask_injuries": "🩺 Есть травмы или ограничения?\n(или «нет»)",
    "ask_diet":     "Особенности питания?\n🍖 Стандарт / 🥦 Вегетарианство / 🌱 Веганство / 🥑 Кето",
    "ask_allergy":  "Аллергии на продукты?\n(или «нет»)",
    "ask_style":    "Как общаться?\n😊 Дружелюбно / 💪 Строго / 😄 С юмором",
}

SLEEP_WORDS = ["спокойной ночи","сплю","иду спать","ложусь","пока спать","ночи"]
FOOD_WORDS  = ["съел","съела","выпил","выпила","поел","поела","перекус",
               "завтрак","обед","ужин","скушал","скушала","перекусил"]

# =============================================
# /START
# =============================================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    tg = message.from_user
    user = db_get_user(tg.id)
    if not user:
        db_create_user(tg.id, tg.username, tg.first_name, tg.last_name)
        db_update_user(tg.id, {"onboarding_step":"ask_age","onboarding_done":False})
        await message.answer(
            f"👋 Привет, {tg.first_name}!\n\nЯ Макс — твой личный тренер и коуч.\nПомогу с тренировками, питанием и расписанием.\n\nДавай познакомимся!\n\n{OB_QUESTIONS['ask_age']}",
            reply_markup=ReplyKeyboardRemove()
        )
    elif not user.get("onboarding_done"):
        step = user.get("onboarding_step","ask_age")
        await message.answer(f"Продолжим! 😊\n\n{OB_QUESTIONS.get(step,'Введи данные:')}", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer(f"С возвращением, {tg.first_name}! 💪\nЧем займёмся?", reply_markup=main_menu())

# =============================================
# ГЛАВНЫЙ ОБРАБОТЧИК
# =============================================

@dp.message(F.text)
async def handle_all(message: Message):
    tg_id = message.from_user.id
    text  = message.text.strip()
    user  = db_get_user(tg_id)

    if not user:
        await cmd_start(message); return
    if user.get("status") == "banned":
        await message.answer("🚫 Аккаунт заблокирован."); return

    db_update_user(tg_id, {"last_active": datetime.utcnow().isoformat()})

    # Онбординг
    if not user.get("onboarding_done"):
        await do_onboarding(message, user, text); return

    # Идёт спать
    if any(w in text.lower() for w in SLEEP_WORDS):
        db_set_sleep(tg_id)
        await message.answer("Спокойной ночи! 😴\nЗапомнил время — утром скажу сколько поспал.", reply_markup=main_menu()); return

    # Меню
    if text == "💪 Тренировка":   await show_workout(message, user); return
    if text == "🥗 Питание":      await show_food_menu(message); return
    if text == "📊 Прогресс":     await show_progress(message, user); return
    if text == "📅 Расписание":   await show_schedule(message, user); return
    if text == "⚙️ Профиль":      await show_profile(message, user); return
    if text == "💬 Спросить Макса": await message.answer("Задай любой вопрос! 💬", reply_markup=main_menu()); return

    # Еда
    if any(w in text.lower() for w in FOOD_WORDS):
        await do_food_log(message, user, text); return

    # Извлекаем данные из сообщения
    extracted = await ai_extract(text)

    # Обес питание по описанию еды
    if extracted.get("food_log"):
        await do_food_log(message, user, text); return

    # Вес — с подтверждением
    if extracted.get("weight"):
        w = extracted["weight"]
        profile = db_get_profile(user["id"])
        old_w = (profile or {}).get("weight")
        preview = f"📊 Обновление веса:\nБыло: {old_w or '?'} кг → Стало: {w} кг"
        if old_w and abs(float(old_w) - float(w)) > 15:
            preview = f"⚠️ Большая разница!\nБыло: {old_w} кг → Стало: {w} кг\n\nЭто точные данные?"
        p = db_create_pending(tg_id, user["id"], "weight", {"weight": w}, preview)
        if p:
            await message.answer(preview, reply_markup=confirm_kb(p["id"])); return

    # Заметки
    if extracted.get("preference"):
        db_save_note(user["id"], "preference", f"p_{int(datetime.now().timestamp())}", extracted["preference"], text)
    if extracted.get("note"):
        db_save_note(user["id"], "context", f"n_{int(datetime.now().timestamp())}", extracted["note"], text)

    # AI чат
    await do_ai_chat(message, user, text)


async def do_ai_chat(message: Message, user: dict, text: str):
    profile  = db_get_profile(user["id"])
    today    = db_today_food(user["id"])
    checkin  = db_get_checkin(user["id"])
    patterns = db_get_patterns(user["id"])
    notes    = db_get_notes(user["id"])
    today_full = {**today, **(checkin or {})}
    typing_msg = await message.answer("✍️")
    reply = await ai_chat(user["id"], text, profile, today_full, patterns, notes)
    await typing_msg.delete()
    await message.answer(reply, reply_markup=main_menu())

# =============================================
# ОНБОРДИНГ
# =============================================

async def do_onboarding(message: Message, user: dict, text: str):
    step = user.get("onboarding_step", "ask_age")
    result = await ai_onboarding(step, text)

    if not result.get("valid"):
        await message.answer(result.get("reply","Попробуй ещё раз 😊")); return

    field = result["field"]
    value = result["value"]

    # Конвертация типов
    int_f   = ["age","height","days_per_week","session_duration","activity_level","travel_time_gym"]
    float_f = ["weight","target_weight"]
    list_f  = ["injuries","food_allergies"]

    if field in int_f:
        try: value = int(float(str(value)))
        except: pass
    elif field in float_f:
        try: value = float(value) if value and str(value).lower() not in ["null","none","не знаю","хз"] else None
        except: value = None
    elif field in list_f:
        if isinstance(value, str):
            clean = value.lower().strip().replace("[","").replace("]","")
            if clean in ["нет","no","none",""]:
                value = []
            else:
                value = [v.strip() for v in clean.split(",") if v.strip()]
        elif not isinstance(value, list):
            value = []

    if value is not None:
        db_update_profile(user["id"], {field: value})

    next_step = result.get("next","completed")

    if next_step == "completed":
        await finish_onboarding(message, user)
    else:
        db_update_user(message.from_user.id, {"onboarding_step": next_step})
        await message.answer(f"✅ Записал!\n\n{OB_QUESTIONS.get(next_step,'')}")


async def finish_onboarding(message: Message, user: dict):
    profile = db_get_profile(user["id"])
    nutrition_text = ""

    if all([profile.get("age"), profile.get("gender"), profile.get("height"),
            profile.get("weight"), profile.get("goal")]):
        activity = profile.get("activity_level") or 2
        stats = calc_bmr_tdee(
            profile["age"], profile["gender"], profile["height"],
            float(profile["weight"]), activity, profile["goal"]
        )
        db_update_profile(user["id"], stats)
        nutrition_text = (
            f"\n\n📊 Твои нормы на день:\n"
            f"🔥 {stats['daily_calories']} ккал\n"
            f"🥩 Белки: {stats['daily_protein']}г | 🥑 Жиры: {stats['daily_fat']}г | 🍞 Углеводы: {stats['daily_carbs']}г"
        )

    supabase.table("users").update({
        "onboarding_done": True, "onboarding_step": "completed"
    }).eq("telegram_id", message.from_user.id).execute()

    goals = {'lose':'похудение 🔥','gain':'набор массы 💪','maintain':'поддержание ⚖️','health':'здоровье ❤️'}
    goal_text = goals.get((profile or {}).get('goal',''), 'твою цель')

    # Ставим дефолтные напоминания
    await setup_default_reminders(user["id"], message.from_user.id, profile)

    await message.answer(
        f"🎉 Отлично, всё записал!\n\n"
        f"Твоя цель — {goal_text}.{nutrition_text}\n\n"
        f"Я буду писать тебе утром и вечером, напоминать о тренировках и следить за прогрессом.\n\n"
        f"Что начнём?",
        reply_markup=main_menu()
    )


async def setup_default_reminders(user_id, telegram_id, profile):
    """Автоматически создаём базовые напоминания"""
    wake = (profile or {}).get("wake_time") or "08:00"
    if isinstance(wake, str) and len(wake) >= 5:
        wake_str = wake[:5]
    else:
        wake_str = "08:00"

    all_days = ["mon","tue","wed","thu","fri","sat","sun"]

    # Утреннее
    db_save_reminder(user_id, telegram_id, "morning", "", wake_str, all_days, use_gpt=True)
    # Вечернее в 21:00
    db_save_reminder(user_id, telegram_id, "evening", "", "21:00", all_days, use_gpt=True)

# =============================================
# CALLBACKS
# =============================================

@dp.callback_query(F.data.startswith("ok_"))
async def cb_confirm(callback: CallbackQuery):
    pid = int(callback.data.split("_")[1])
    action = db_get_pending(pid)
    if not action:
        await callback.answer("Устарело"); return

    user = db_get_user(callback.from_user.id)
    atype = action["action_type"]
    adata = action["action_data"]

    if atype == "weight":
        w = float(adata["weight"])
        db_update_profile(user["id"], {"weight": w})
        db_save_checkin(user["id"], {"weight": w})
        db_confirm_pending(pid)
        await callback.message.edit_text(f"✅ Вес {w} кг сохранён!")

    elif atype == "plan":
        db_save_plan(user["id"], adata["plan"])
        db_confirm_pending(pid)
        await callback.message.edit_text("✅ План сохранён! Напиши «💪 Тренировка» чтобы посмотреть.")


@dp.callback_query(F.data.startswith("no_"))
async def cb_cancel(callback: CallbackQuery):
    pid = int(callback.data.split("_")[1])
    db_cancel_pending(pid)
    await callback.message.edit_text("❌ Отменено")


@dp.callback_query(F.data.startswith("nrg_"))
async def cb_energy(callback: CallbackQuery):
    level = int(callback.data.split("_")[1])
    user = db_get_user(callback.from_user.id)
    db_save_checkin(user["id"], {"energy_level": level})

    sleep_h = db_calc_sleep(user["id"], callback.from_user.id)
    words = {1:"Понял, бережём силы сегодня 🙏", 3:"Хорошо, средний темп сегодня!", 5:"Огонь! 🔥 Отличный настрой!"}
    msg = words.get(level, "Записал!")

    if sleep_h:
        msg += f"\n😴 Поспал {sleep_h} ч — {'маловато, сделаем лёгкую тренировку' if sleep_h < 6 else 'хорошо!'}"

    if level <= 2:
        await callback.message.edit_text(msg)
        await callback.message.answer("Как насчёт тренировки?", reply_markup=workout_adapt_kb())
    else:
        await callback.message.edit_text(msg)


@dp.callback_query(F.data.startswith("wkt_"))
async def cb_workout(callback: CallbackQuery):
    choice = callback.data.split("_")[1]
    user = db_get_user(callback.from_user.id)
    if choice == "skip":
        db_save_checkin(user["id"], {"workout_done": False})
        await callback.message.edit_text("Окей, отдыхаем 😴 Завтра наверстаем!")
    else:
        db_save_checkin(user["id"], {"workout_done": True})
        note = "лёгкую" if choice == "light" else "полную"
        await callback.message.edit_text(f"💪 Отлично! Идёшь на {note} тренировку. Удачи!")

# =============================================
# ТРЕНИРОВКИ
# =============================================

async def show_workout(message: Message, user: dict):
    plan = db_get_plan(user["id"])
    if plan:
        await message.answer(
            f"💪 Твой план:\n\n{plan['plan_text']}\n\nНапиши «новый план» для обновления.",
            reply_markup=main_menu()
        )
    else:
        profile = db_get_profile(user["id"])
        if not profile or not profile.get("goal"):
            await message.answer("Сначала заполни анкету — /start", reply_markup=main_menu()); return
        msg = await message.answer("⏳ Составляю персональный план...")
        plan_text = await ai_workout_plan(profile)
        await msg.delete()
        p = db_create_pending(message.from_user.id, user["id"], "plan", {"plan": plan_text}, "")
        if p:
            await message.answer(
                f"📅 Вот твой план:\n\n{plan_text}\n\nСохраняем?",
                reply_markup=confirm_kb(p["id"])
            )

# =============================================
# ПИТАНИЕ
# =============================================

async def show_food_menu(message: Message):
    await message.answer(
        "🥗 Трекинг питания\n\n"
        "Напиши что съел, например:\n"
        "• «съел 3 яйца и тост»\n"
        "• «обед: борщ 300г и хлеб»\n"
        "• «выпил протеин 30г»\n\n"
        "Посчитаю КБЖУ и скажу остаток до нормы 👇",
        reply_markup=main_menu()
    )


async def do_food_log(message: Message, user: dict, text: str):
    typing = await message.answer("⏳ Считаю КБЖУ...")
    nutrition = await ai_kbju(text)
    await typing.delete()

    if not nutrition:
        await message.answer("Не смог посчитать. Опиши подробнее 🙏", reply_markup=main_menu()); return

    db_log_food(user["id"], text,
                nutrition["calories"], nutrition["protein"],
                nutrition["fat"], nutrition["carbs"],
                nutrition.get("is_approximate", False))

    today = db_today_food(user["id"])
    profile = db_get_profile(user["id"])
    daily_cal  = (profile or {}).get("daily_calories") or 2000
    daily_prot = (profile or {}).get("daily_protein") or 150
    rem_cal    = daily_cal - today["calories"]
    rem_prot   = daily_prot - today["protein"]
    approx     = "~" if nutrition.get("is_approximate") else ""

    await message.answer(
        f"✅ {nutrition.get('description', text)}\n\n"
        f"🔥 {approx}{nutrition['calories']} ккал\n"
        f"🥩 Б: {approx}{nutrition['protein']}г | 🥑 Ж: {approx}{nutrition['fat']}г | 🍞 У: {approx}{nutrition['carbs']}г\n\n"
        f"━━━━━━━━━━\n"
        f"📈 За день: {round(today['calories'])} / {round(daily_cal)} ккал\n"
        f"{'✅' if rem_cal > 0 else '⚠️'} Осталось: {round(rem_cal)} ккал | Белок: {round(rem_prot)}г",
        reply_markup=main_menu()
    )

# =============================================
# ПРОГРЕСС
# =============================================

async def show_progress(message: Message, user: dict):
    profile = db_get_profile(user["id"]) or {}
    today   = db_today_food(user["id"])
    checkin = db_get_checkin(user["id"])
    daily_cal = profile.get("daily_calories") or 2000
    goals = {'lose':'похудение','gain':'набор','maintain':'поддержание','health':'здоровье'}
    sleep_str  = f"{checkin.get('sleep_hours')} ч" if checkin and checkin.get('sleep_hours') else "не записан"
    energy_str = f"{checkin.get('energy_level')}/5" if checkin and checkin.get('energy_level') else "—"

    await message.answer(
        f"📊 {date.today().strftime('%d.%m.%Y')}\n\n"
        f"⚖️ Вес: {profile.get('weight','?')} кг | Цель: {goals.get(profile.get('goal'),'?')}\n"
        f"😴 Сон: {sleep_str} | ⚡ Энергия: {energy_str}\n\n"
        f"🍽 Питание сегодня:\n"
        f"🔥 {round(today['calories'])} / {round(daily_cal)} ккал\n"
        f"🥩 Б: {round(today['protein'])}г | 🥑 Ж: {round(today['fat'])}г | 🍞 У: {round(today['carbs'])}г",
        reply_markup=main_menu()
    )

# =============================================
# РАСПИСАНИЕ
# =============================================

async def show_schedule(message: Message, user: dict):
    schedule = db_get_schedule(user["id"])
    if not schedule:
        await message.answer(
            "📅 Расписание не настроено.\n\n"
            "Расскажи мне:\n"
            "• Во сколько просыпаешься?\n"
            "• Когда работаешь?\n"
            "• Когда удобно тренироваться?\n\n"
            "Напиши всё сразу — я разберусь!",
            reply_markup=main_menu()
        )
    else:
        days_ru = {'mon':'Пн','tue':'Вт','wed':'Ср','thu':'Чт','fri':'Пт','sat':'Сб','sun':'Вс'}
        text = "📅 Твоё расписание:\n\n"
        for s in schedule:
            day = days_ru.get(s['day_of_week'], s['day_of_week'])
            if s.get('is_rest_day'):
                text += f"{day}: 😴 Отдых\n"
            else:
                work = f"{s.get('work_start','')}–{s.get('work_end','')}" if s.get('work_start') else "нет"
                text += f"{day}: 🌅{s.get('wake_time','?')} | 💼{work} | 💪{s.get('workout_time','?')}\n"
        text += "\nЧтобы изменить — просто напиши, например:\n«перенеси тренировку в среду на 19:00»"
        await message.answer(text, reply_markup=main_menu())

# =============================================
# ПРОФИЛЬ
# =============================================

async def show_profile(message: Message, user: dict):
    p = db_get_profile(user["id"]) or {}
    goals = {'lose':'похудение','gain':'набор массы','maintain':'поддержание','health':'здоровье'}
    exp   = {'beginner':'новичок','intermediate':'средний','advanced':'продвинутый'}
    await message.answer(
        f"⚙️ Профиль\n\n"
        f"👤 {user.get('first_name','')} | "
        f"📅 {p.get('age','?')} лет | "
        f"{'♂️' if p.get('gender')=='male' else '♀️' if p.get('gender')=='female' else '?'}\n"
        f"📏 {p.get('height','?')} см | ⚖️ {p.get('weight','?')} кг → 🎯 {p.get('target_weight','?')} кг\n"
        f"🏆 Цель: {goals.get(p.get('goal'),'?')} | 💪 {exp.get(p.get('experience'),'?')}\n"
        f"🏋️ {p.get('equipment','?')} | {p.get('days_per_week','?')} дн/нед | {p.get('session_duration','?')} мин\n"
        f"🩺 Травмы: {', '.join(p.get('injuries') or []) or 'нет'}\n\n"
        f"🔥 {round(p.get('daily_calories') or 0)} ккал/день\n"
        f"Б:{round(p.get('daily_protein') or 0)}г | Ж:{round(p.get('daily_fat') or 0)}г | У:{round(p.get('daily_carbs') or 0)}г\n\n"
        f"Чтобы обновить — /start",
        reply_markup=main_menu()
    )

# =============================================
# SCHEDULER (напоминания)
# =============================================

async def scheduler():
    """Каждую минуту проверяем напоминания"""
    days_map = {0:'mon',1:'tue',2:'wed',3:'thu',4:'fri',5:'sat',6:'sun'}
    print("⏰ Scheduler запущен")
    while True:
        try:
            now = datetime.utcnow()
            current_time = now.strftime("%H:%M")
            current_day  = days_map[now.weekday()]
            due = db_get_due_reminders(current_time, current_day)

            for rem in due:
                try:
                    tg_id   = rem["telegram_id"]
                    user    = db_get_user(tg_id)
                    if not user or user.get("status") == "banned":
                        continue

                    profile  = db_get_profile(user["id"])
                    today    = db_today_food(user["id"])
                    checkin  = db_get_checkin(user["id"])
                    patterns = db_get_patterns(user["id"])
                    notes    = db_get_notes(user["id"])
                    today_full = {**today, **(checkin or {})}

                    rtype = rem["type"]

                    if rem.get("use_gpt"):
                        text = await ai_reminder(rtype, profile, today_full, patterns, notes)
                    else:
                        text = rem.get("message","")

                    if rtype == "morning":
                        await bot.send_message(tg_id, text, reply_markup=energy_kb())
                    else:
                        await bot.send_message(tg_id, text, reply_markup=main_menu())

                    # Обновляем last_sent
                    supabase.table("reminders").update({
                        "last_sent": datetime.utcnow().isoformat()
                    }).eq("id", rem["id"]).execute()

                except Exception as e:
                    print(f"Reminder error {rem.get('id')}: {e}")

        except Exception as e:
            print(f"Scheduler error: {e}")

        await asyncio.sleep(60)

# =============================================
# ADMIN
# =============================================

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    user = db_get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin","superadmin"]: return
    stats = db_get_stats()
    await message.answer(
        f"👑 Админ\n\n"
        f"👥 Всего: {stats['total']} | ✅ Активных: {stats['active']} | 📋 С анкетой: {stats['onboarded']}\n\n"
        f"/ban [id] — забанить\n/unban [id] — разбанить\n/broadcast [текст] — рассылка"
    )

@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    user = db_get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin","superadmin"]: return
    args = message.text.split()
    if len(args) < 2: await message.answer("/ban [id]"); return
    db_ban(int(args[1]))
    await message.answer(f"✅ Забанен {args[1]}")

@dp.message(Command("unban"))
async def cmd_unban(message: Message):
    user = db_get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin","superadmin"]: return
    args = message.text.split()
    if len(args) < 2: await message.answer("/unban [id]"); return
    db_unban(int(args[1]))
    await message.answer(f"✅ Разбанен {args[1]}")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    user = db_get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin","superadmin"]: return
    text = message.text.replace("/broadcast","").strip()
    if not text: await message.answer("/broadcast [текст]"); return
    users = db_get_all_users("active")
    sent = 0
    for u in users:
        try:
            await bot.send_message(u["telegram_id"], text)
            sent += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Отправлено: {sent}/{len(users)}")

# =============================================
# ЗАПУСК
# =============================================

async def main():
    print("🤖 FitBot запущен!")
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

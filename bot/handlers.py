import os
import asyncio
import json
import re
from datetime import datetime, date
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

bot    = Bot(token=os.getenv("TELEGRAM_TOKEN"))
dp     = Dispatcher(storage=MemoryStorage())
openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL  = "gpt-4o-mini"

supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)

# ─────────────────────────────────────────────
# КЛАВИАТУРЫ
# ─────────────────────────────────────────────

def main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💪 Тренировка"), KeyboardButton(text="🥗 Питание")],
        [KeyboardButton(text="📊 Прогресс"),   KeyboardButton(text="📅 Расписание")],
        [KeyboardButton(text="⚙️ Профиль"),    KeyboardButton(text="💬 Спросить Макса")]
    ], resize_keyboard=True)

def energy_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="😴 Устал",  callback_data="nrg_1"),
        InlineKeyboardButton(text="😐 Норм",   callback_data="nrg_3"),
        InlineKeyboardButton(text="⚡ Огонь",  callback_data="nrg_5"),
    ]])

def yesno_kb(action, pid):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да",  callback_data=f"yes_{action}_{pid}"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"nope_{action}_{pid}"),
    ]])

# ─────────────────────────────────────────────
# БД
# ─────────────────────────────────────────────

def db(table): return supabase.table(table)

def get_user(tid):
    r = db("users").select("*").eq("telegram_id", tid).execute()
    return r.data[0] if r.data else None

def create_user(tid, username, first_name, last_name=None):
    r = db("users").insert({"telegram_id":tid,"username":username,
                             "first_name":first_name,"last_name":last_name}).execute()
    return r.data[0] if r.data else None

def update_user(tid, data):
    db("users").update(data).eq("telegram_id", tid).execute()

def get_profile(uid):
    r = db("profile").select("*").eq("user_id", uid).execute()
    return r.data[0] if r.data else {}

def save_profile(uid, data):
    data["updated_at"] = datetime.utcnow().isoformat()
    db("profile").update(data).eq("user_id", uid).execute()

def add_message(uid, role, content):
    db("messages").insert({"user_id":uid,"role":role,"content":content}).execute()

def get_history(uid, limit=20):
    r = db("messages").select("role,content").eq("user_id",uid)\
        .order("created_at",desc=True).limit(limit).execute()
    return list(reversed(r.data or []))

def log_food(uid, desc, cal, prot, fat, carbs, approx=False):
    db("nutrition_log").insert({"user_id":uid,"food_description":desc,
        "calories":cal,"protein":prot,"fat":fat,"carbs":carbs,
        "is_approximate":approx}).execute()

def today_food(uid):
    today = date.today().isoformat()
    r = db("nutrition_log").select("*").eq("user_id",uid)\
        .gte("logged_at",f"{today}T00:00:00").execute()
    t = {"calories":0.0,"protein":0.0,"fat":0.0,"carbs":0.0}
    for i in (r.data or []):
        t["calories"] += i.get("calories") or 0
        t["protein"]  += i.get("protein")  or 0
        t["fat"]      += i.get("fat")      or 0
        t["carbs"]    += i.get("carbs")    or 0
    return t

def save_plan(uid, text):
    db("workout_plans").update({"is_active":False}).eq("user_id",uid).execute()
    db("workout_plans").insert({"user_id":uid,"plan_text":text,
        "week_start":date.today().isoformat(),"is_active":True}).execute()

def get_plan(uid):
    r = db("workout_plans").select("*").eq("user_id",uid).eq("is_active",True).execute()
    return r.data[0] if r.data else None

def save_checkin(uid, data):
    today = date.today().isoformat()
    data.update({"user_id":uid,"date":today})
    ex = db("daily_checkins").select("id").eq("user_id",uid).eq("date",today).execute()
    if ex.data:
        db("daily_checkins").update(data).eq("user_id",uid).eq("date",today).execute()
    else:
        db("daily_checkins").insert(data).execute()

def get_checkin(uid):
    r = db("daily_checkins").select("*").eq("user_id",uid)\
        .eq("date",date.today().isoformat()).execute()
    return r.data[0] if r.data else {}

def save_note(uid, key, value, source=None):
    ex = db("user_notes").select("id").eq("user_id",uid).eq("key",key).execute()
    if ex.data:
        db("user_notes").update({"value":value,"source":source,
            "last_mentioned":datetime.utcnow().isoformat()})\
            .eq("user_id",uid).eq("key",key).execute()
    else:
        db("user_notes").insert({"user_id":uid,"category":"auto",
            "key":key,"value":value,"source":source}).execute()

def get_notes(uid):
    r = db("user_notes").select("*").eq("user_id",uid).eq("is_active",True).execute()
    return r.data or []

def set_sleep(tid):
    db("users").update({"sleep_time_last":datetime.utcnow().isoformat()})\
        .eq("telegram_id",tid).execute()

def calc_sleep(uid, tid):
    r = db("users").select("sleep_time_last").eq("telegram_id",tid).execute()
    if not r.data or not r.data[0].get("sleep_time_last"):
        return None
    t = datetime.fromisoformat(r.data[0]["sleep_time_last"].replace("Z",""))
    h = round((datetime.utcnow()-t).seconds/3600, 1)
    if 2 <= h <= 14:
        save_checkin(uid, {"sleep_hours":h})
        return h
    return None

def save_reminder(uid, tid, rtype, time_str, days, message=""):
    db("reminders").insert({"user_id":uid,"telegram_id":tid,"type":rtype,
        "message":message,"time_of_day":time_str,"days_of_week":days,
        "use_gpt":True,"is_active":True}).execute()

def get_due_reminders(cur_time, day):
    r = db("reminders").select("*").eq("is_active",True).execute()
    return [x for x in (r.data or [])
            if (x.get("time_of_day") or "")[:5]==cur_time and day in (x.get("days_of_week") or [])]

def get_all_users(status="active"):
    r = db("users").select("*").eq("status",status).execute()
    return r.data or []

def get_stats():
    t = db("users").select("id",count="exact").execute()
    a = db("users").select("id",count="exact").eq("status","active").execute()
    o = db("users").select("id",count="exact").eq("onboarding_done",True).execute()
    return {"total":t.count or 0,"active":a.count or 0,"onboarded":o.count or 0}

def calc_nutrition_goals(age, gender, height, weight, activity, goal):
    bmr = 10*weight + 6.25*height - 5*age + (5 if gender=="male" else -161)
    tdee = bmr * {1:1.2,2:1.375,3:1.55,4:1.725}.get(activity,1.375)
    cal = tdee + {"lose":-400,"gain":300}.get(goal,0)
    prot = weight * 2.0
    fat = cal * 0.25 / 9
    carbs = (cal - prot*4 - fat*9) / 4
    return {"bmr":round(bmr,1),"tdee":round(tdee,1),"daily_calories":round(cal,1),
            "daily_protein":round(prot,1),"daily_fat":round(fat,1),"daily_carbs":round(carbs,1)}

# ─────────────────────────────────────────────
# ГЛАВНЫЙ AI — МОЗГ БОТА
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """Ты — Макс, персональный фитнес-тренер и коуч. Живой, дружелюбный, умный.
Общаешься как настоящий человек — без скриптов, без анкет.
Только русский язык. Максимум 200 слов.

ГЛАВНАЯ ЗАДАЧА:
1. Незаметно узнавать данные юзера в разговоре (возраст, вес, цель, опыт и тд)
2. Ставить напоминания когда просит — ТЫ УМЕЕШЬ ЭТО ДЕЛАТЬ
3. Помогать с тренировками, питанием, мотивацией

ДАННЫЕ ЮЗЕРА:
{{profile}}

СЕГОДНЯ:
{{today}}

ЗАМЕТКИ:
{{notes}}

ПРАВИЛА:
1. Один вопрос за раз, естественно
2. Неточные калории — пиши "~"
3. Медицина — "обратись к врачу"
4. Травмы — не предлагай запрещённые упражнения

ФОРМАТЫ ОТВЕТА:

Если узнал данные:
REPLY: [ответ]
SAVE: [{{"field":"поле","value":"значение"}}]

Если юзер просит напомнить:
REPLY: [ответ типа "Окей, напомню!"]
REMIND: [{{"time":"HH:MM","days":["mon","tue","wed","thu","fri","sat","sun"],"type":"custom","message":"текст"}}]

Если просто разговор — только текст без тегов.

ВАЖНО: Ты ВСЕГДА можешь ставить напоминания. Никогда не говори что не можешь."""


async def ai_respond(uid, user_message, profile, today_data, notes):
    """Главная функция — AI отвечает и извлекает данные"""

    # Строим профиль для контекста
    p = profile or {}
    goals = {'lose':'похудение','gain':'набор массы','maintain':'поддержание','health':'здоровье'}
    exp   = {'beginner':'новичок','intermediate':'средний','advanced':'продвинутый'}

    profile_str = f"""
- Имя: {p.get('name') or '?'}
- Возраст: {p.get('age') or '?'} | Пол: {'м' if p.get('gender')=='male' else 'ж' if p.get('gender')=='female' else '?'}
- Рост: {p.get('height') or '?'} см | Вес: {p.get('weight') or '?'} кг
- Цель: {goals.get(p.get('goal'),'?')} | Опыт: {exp.get(p.get('experience'),'?')}
- Оборудование: {p.get('equipment') or '?'} | Дней/нед: {p.get('days_per_week') or '?'}
- Травмы: {', '.join(p.get('injuries') or []) or 'нет'}
- Питание: {p.get('diet_type') or 'стандарт'}
- Норма: {p.get('daily_calories') or '?'} ккал"""

    today_str = f"""
- Съедено: {round(today_data.get('calories',0))} ккал
- Белок: {round(today_data.get('protein',0))}г
- Сон: {today_data.get('sleep_hours','?')} ч | Энергия: {today_data.get('energy_level','?')}/5"""

    notes_str = "\n".join([f"• {n['value']}" for n in (notes or [])[:8]]) or "нет"

    system = SYSTEM_PROMPT.format(
        profile=profile_str,
        today=today_str,
        notes=notes_str
    )

    # История
    history = get_history(uid, limit=20)
    msgs = [{"role":"system","content":system}]
    msgs += [{"role":m["role"],"content":m["content"]} for m in history]
    msgs.append({"role":"user","content":user_message})

    r = await openai.chat.completions.create(
        model=MODEL, messages=msgs, max_tokens=500, temperature=0.85
    )
    raw = r.choices[0].message.content

    # Парсим ответ
    reply_text  = raw
    save_data   = None
    remind_data = None

    if "REPLY:" in raw:
        try:
            reply_part = re.search(r'REPLY:\s*(.*?)(?=SAVE:|REMIND:|$)', raw, re.DOTALL)
            if reply_part: reply_text = reply_part.group(1).strip()
        except: pass

    if "SAVE:" in raw:
        try:
            save_part = re.search(r'SAVE:\s*(\[.*?\]|\{.*?\})', raw, re.DOTALL)
            if save_part:
                parsed = json.loads(save_part.group(1))
                save_data = parsed if isinstance(parsed, dict) else parsed[0] if parsed else None
        except: pass

    if "REMIND:" in raw:
        try:
            remind_part = re.search(r'REMIND:\s*(\[.*?\]|\{.*?\})', raw, re.DOTALL)
            if remind_part:
                parsed = json.loads(remind_part.group(1))
                remind_data = parsed if isinstance(parsed, dict) else parsed[0] if parsed else None
        except: pass

    # Сохраняем сообщения
    add_message(uid, "user",      user_message)
    add_message(uid, "assistant", reply_text)

    return reply_text, save_data, remind_data


async def ai_kbju(food_text):
    """Считаем КБЖУ"""
    r = await openai.chat.completions.create(
        model=MODEL,
        messages=[
            {"role":"system","content":"Ты диетолог. Считай КБЖУ точно. Только JSON."},
            {"role":"user","content":
             f'КБЖУ для: "{food_text}". JSON: {{"calories":число,"protein":число,"fat":число,"carbs":число,"description":"что посчитал","is_approximate":true/false}}'}
        ],
        max_tokens=150, temperature=0.1
    )
    try:
        m = re.search(r'\{[\s\S]*\}', r.choices[0].message.content)
        if m: return json.loads(m.group(0))
    except: pass
    return None


async def ai_workout_plan(profile):
    """Генерим план тренировок"""
    injuries = ', '.join(profile.get('injuries') or []) or 'нет'
    r = await openai.chat.completions.create(
        model=MODEL,
        messages=[
            {"role":"system","content":"Ты тренер. Учитывай травмы — это критично для безопасности юзера."},
            {"role":"user","content":
             f"""Составь план тренировок на неделю:
Цель: {profile.get('goal')} | Опыт: {profile.get('experience')}
Дней: {profile.get('days_per_week',3)} | По {profile.get('session_duration',60)} мин
Оборудование: {profile.get('equipment')} | Травмы (ИСКЛЮЧИТЬ): {injuries}

Формат:
📅 ПЛАН НА НЕДЕЛЮ
День 1 — [название]:
• Упражнение — подходы×повторения
...
Дни отдыха: [дни]
💡 Главный совет: [1 предложение]"""}
        ],
        max_tokens=900, temperature=0.5
    )
    return r.choices[0].message.content


async def ai_reminder_text(rtype, profile, today_data, notes):
    """Живые напоминания через GPT"""
    p = profile or {}
    ctx = f"Юзер: {p.get('age','?')} лет, цель: {p.get('goal','?')}, вес: {p.get('weight','?')} кг. Сегодня съел {round(today_data.get('calories',0))} ккал."
    texts = {
        "morning": "Напиши доброе утро и мотивацию на день. 2-3 живых предложения.",
        "evening": "Вечерний итог дня. Кратко — что хорошо, что завтра. 3 предложения.",
        "workout": "Напомни о тренировке. Мотивирующе. 1-2 предложения.",
        "water":   "Напомни выпить воду. С лёгким юмором. 1 предложение.",
    }
    r = await openai.chat.completions.create(
        model=MODEL,
        messages=[{"role":"system","content":f"Ты тренер Макс. {ctx}"},
                  {"role":"user","content":texts.get(rtype,"Короткое мотивирующее.")}],
        max_tokens=150, temperature=0.9
    )
    return r.choices[0].message.content

# ─────────────────────────────────────────────
# ПОЛЯ ПРОФИЛЯ — маппинг
# ─────────────────────────────────────────────

PROFILE_FIELDS = {
    "age","gender","height","weight","target_weight","goal","experience",
    "days_per_week","session_duration","equipment","wake_time","work_type",
    "travel_time_gym","injuries","diet_type","food_allergies",
    "communication_style","activity_level"
}

INT_FIELDS   = {"age","height","days_per_week","session_duration","activity_level","travel_time_gym"}
FLOAT_FIELDS = {"weight","target_weight"}
LIST_FIELDS  = {"injuries","food_allergies"}

def convert_value(field, value):
    """Конвертируем значение в нужный тип"""
    if value is None or str(value).lower() in ["null","none","не знаю","хз","?"]:
        return None
    if field in INT_FIELDS:
        try: return int(float(str(value)))
        except: return None
    if field in FLOAT_FIELDS:
        try: return float(str(value))
        except: return None
    if field in LIST_FIELDS:
        if isinstance(value, list): return value
        s = str(value).lower().strip().replace("[","").replace("]","")
        if s in ["нет","no","none",""]: return []
        return [v.strip() for v in s.split(",") if v.strip()]
    return value

# ─────────────────────────────────────────────
# ОБРАБОТЧИКИ
# ─────────────────────────────────────────────

SLEEP_WORDS = ["спокойной ночи","сплю","иду спать","ложусь","спать ","ночи"]
FOOD_WORDS  = ["съел","съела","выпил","выпила","поел","поела","перекус",
               "завтрак","обед","ужин","скушал","скушала","перекусил"]


@dp.message(CommandStart())
async def cmd_start(message: Message):
    tg = message.from_user
    user = get_user(tg.id)

    if not user:
        create_user(tg.id, tg.username, tg.first_name, tg.last_name)
        update_user(tg.id, {"onboarding_done": False})

        # Первое сообщение — через AI, живо
        first_reply, _ = await ai_respond(
            user_id_from_tg(tg.id),
            f"Привет! Меня зовут {tg.first_name}",
            {}, {}, []
        )
        await message.answer(first_reply, reply_markup=ReplyKeyboardRemove())

    elif user.get("status") == "banned":
        await message.answer("🚫 Аккаунт заблокирован.")
    else:
        await message.answer(
            f"С возвращением, {tg.first_name}! 💪\nЧем займёмся?",
            reply_markup=main_menu()
        )


def user_id_from_tg(tid):
    """Получаем user_id по telegram_id"""
    r = supabase.table("users").select("id").eq("telegram_id", tid).execute()
    return r.data[0]["id"] if r.data else None


@dp.message(F.text)
async def handle_all(message: Message):
    tg_id = message.from_user.id
    text  = message.text.strip()
    user  = get_user(tg_id)

    if not user:
        await cmd_start(message); return
    if user.get("status") == "banned":
        await message.answer("🚫 Аккаунт заблокирован."); return

    update_user(tg_id, {"last_active": datetime.utcnow().isoformat()})

    uid     = user["id"]
    profile = get_profile(uid)
    today   = {**today_food(uid), **(get_checkin(uid) or {})}
    notes   = get_notes(uid)

    # Идёт спать
    if any(w in text.lower() for w in SLEEP_WORDS):
        set_sleep(tg_id)
        reply, _ = await ai_respond(uid, text, profile, today, notes)
        await message.answer(reply, reply_markup=main_menu()); return

    # Меню кнопки
    if text == "💪 Тренировка":
        await handle_workout(message, uid, profile); return
    if text == "🥗 Питание":
        await handle_food_info(message); return
    if text == "📊 Прогресс":
        await handle_progress(message, uid, profile, today); return
    if text == "📅 Расписание":
        await handle_schedule(message, uid); return
    if text == "⚙️ Профиль":
        await handle_profile_view(message, uid, user, profile); return
    if text == "💬 Спросить Макса":
        await message.answer("Задай любой вопрос! 💬", reply_markup=main_menu()); return

    # Еда
    if any(w in text.lower() for w in FOOD_WORDS):
        await handle_food_log(message, uid, profile, today, text); return

    # Главный AI обработчик
    reply, save_data, remind_data = await ai_respond(uid, text, profile, today, notes)

    # Сохраняем напоминание если AI его создал
    if remind_data and isinstance(remind_data, dict):
        try:
            save_reminder(uid, tg_id,
                remind_data.get("type","custom"),
                remind_data.get("time","09:00"),
                remind_data.get("days", ["mon","tue","wed","thu","fri","sat","sun"]),
                remind_data.get("message",""))
        except Exception as e:
            print(f"Reminder save error: {e}")

    # Сохраняем данные если AI их извлёк
    if save_data and isinstance(save_data, dict):
        field = save_data.get("field")
        value = save_data.get("value")

        if field and field in PROFILE_FIELDS:
            converted = convert_value(field, value)
            if converted is not None:
                save_profile(uid, {field: converted})

                # Если получили все основные данные — считаем нормы
                p = get_profile(uid)
                if all([p.get("age"), p.get("gender"), p.get("height"),
                        p.get("weight"), p.get("goal")]):
                    activity = p.get("activity_level") or 2
                    stats = calc_nutrition_goals(
                        p["age"], p["gender"], p["height"],
                        float(p["weight"]), activity, p["goal"]
                    )
                    save_profile(uid, stats)

                    # Помечаем онбординг завершённым
                    if not user.get("onboarding_done"):
                        update_user(tg_id, {"onboarding_done": True})
                        # Ставим напоминания
                        wake = p.get("wake_time") or "08:00"
                        if isinstance(wake, str): wake = wake[:5]
                        all_days = ["mon","tue","wed","thu","fri","sat","sun"]
                        save_reminder(uid, tg_id, "morning", wake, all_days, "")
                        save_reminder(uid, tg_id, "evening", "21:00", all_days, "")

        elif field == "note":
            save_note(uid, f"note_{int(datetime.now().timestamp())}", str(value), text)

    # Показываем меню если онбординг завершён
    markup = main_menu() if user.get("onboarding_done") else ReplyKeyboardRemove()
    await message.answer(reply, reply_markup=markup)


# ─────────────────────────────────────────────
# ТРЕНИРОВКИ
# ─────────────────────────────────────────────

async def handle_workout(message: Message, uid, profile):
    plan = get_plan(uid)
    if plan:
        await message.answer(
            f"💪 Твой план:\n\n{plan['plan_text']}\n\n"
            f"Написать «новый план» чтобы обновить.",
            reply_markup=main_menu()
        )
    else:
        if not profile.get("goal"):
            await message.answer(
                "Расскажи мне сначала о своей цели и параметрах — "
                "тогда составлю идеальный план!",
                reply_markup=main_menu()
            ); return
        await message.answer("⏳ Составляю персональный план...")
        plan_text = await ai_workout_plan(profile)
        save_plan(uid, plan_text)
        await message.answer(
            f"📅 Вот твой план:\n\n{plan_text}",
            reply_markup=main_menu()
        )


# ─────────────────────────────────────────────
# ПИТАНИЕ
# ─────────────────────────────────────────────

async def handle_food_info(message: Message):
    await message.answer(
        "🥗 Напиши что съел — посчитаю КБЖУ!\n\n"
        "Например: «съел 3 яйца и тост» или «обед: борщ 300г»",
        reply_markup=main_menu()
    )

async def handle_food_log(message: Message, uid, profile, today, text):
    await message.answer("⏳ Считаю КБЖУ...")
    n = await ai_kbju(text)
    if not n:
        await message.answer("Не смог посчитать. Опиши подробнее 🙏", reply_markup=main_menu()); return

    log_food(uid, text, n["calories"], n["protein"], n["fat"], n["carbs"], n.get("is_approximate",False))
    updated = today_food(uid)
    daily   = (profile or {}).get("daily_calories") or 2000
    d_prot  = (profile or {}).get("daily_protein") or 150
    rem     = daily - updated["calories"]
    approx  = "~" if n.get("is_approximate") else ""

    await message.answer(
        f"✅ {n.get('description', text)}\n\n"
        f"🔥 {approx}{n['calories']} ккал | "
        f"🥩 Б:{approx}{n['protein']}г | "
        f"🥑 Ж:{approx}{n['fat']}г | "
        f"🍞 У:{approx}{n['carbs']}г\n\n"
        f"━━━━━━━━\n"
        f"📈 За день: {round(updated['calories'])} / {round(daily)} ккал\n"
        f"{'✅' if rem>0 else '⚠️'} Осталось: {round(rem)} ккал | "
        f"Белок: {round(d_prot-updated['protein'])}г",
        reply_markup=main_menu()
    )


# ─────────────────────────────────────────────
# ПРОГРЕСС
# ─────────────────────────────────────────────

async def handle_progress(message: Message, uid, profile, today):
    p = profile or {}
    goals = {'lose':'похудение','gain':'набор','maintain':'поддержание','health':'здоровье'}
    daily = p.get("daily_calories") or 2000
    sleep = today.get("sleep_hours")
    nrg   = today.get("energy_level")

    await message.answer(
        f"📊 {date.today().strftime('%d.%m.%Y')}\n\n"
        f"⚖️ Вес: {p.get('weight','?')} кг | "
        f"🎯 Цель: {goals.get(p.get('goal'),'?')}\n"
        f"😴 Сон: {f'{sleep} ч' if sleep else 'не записан'} | "
        f"⚡ Энергия: {f'{nrg}/5' if nrg else '—'}\n\n"
        f"🍽 Питание:\n"
        f"🔥 {round(today.get('calories',0))} / {round(daily)} ккал\n"
        f"🥩 Б:{round(today.get('protein',0))}г | "
        f"🥑 Ж:{round(today.get('fat',0))}г | "
        f"🍞 У:{round(today.get('carbs',0))}г",
        reply_markup=main_menu()
    )


# ─────────────────────────────────────────────
# РАСПИСАНИЕ
# ─────────────────────────────────────────────

async def handle_schedule(message: Message, uid):
    r = db("schedule").select("*").eq("user_id", uid).execute()
    schedule = r.data or []
    if not schedule:
        await message.answer(
            "📅 Расписание не настроено.\n\n"
            "Просто расскажи мне:\n"
            "• Во сколько просыпаешься?\n"
            "• Когда работаешь?\n"
            "• Когда удобно тренироваться?\n\n"
            "Напиши всё — я разберусь! 😊",
            reply_markup=main_menu()
        )
    else:
        days = {'mon':'Пн','tue':'Вт','wed':'Ср','thu':'Чт','fri':'Пт','sat':'Сб','sun':'Вс'}
        txt = "📅 Расписание:\n\n"
        for s in schedule:
            d = days.get(s['day_of_week'], s['day_of_week'])
            if s.get('is_rest_day'):
                txt += f"{d}: 😴 Отдых\n"
            else:
                work = f"{s.get('work_start','')}-{s.get('work_end','')}" if s.get('work_start') else "нет"
                txt += f"{d}: 🌅{s.get('wake_time','?')} | 💼{work} | 💪{s.get('workout_time','?')}\n"
        txt += "\nЧтобы изменить — просто напиши мне!"
        await message.answer(txt, reply_markup=main_menu())


# ─────────────────────────────────────────────
# ПРОФИЛЬ
# ─────────────────────────────────────────────

async def handle_profile_view(message: Message, uid, user, profile):
    p = profile or {}
    goals = {'lose':'похудение','gain':'набор массы','maintain':'поддержание','health':'здоровье'}
    exp   = {'beginner':'новичок','intermediate':'средний','advanced':'продвинутый'}
    await message.answer(
        f"⚙️ Профиль\n\n"
        f"👤 {user.get('first_name','')} | "
        f"{'♂️' if p.get('gender')=='male' else '♀️' if p.get('gender')=='female' else '?'} | "
        f"{p.get('age','?')} лет\n"
        f"📏 {p.get('height','?')} см | ⚖️ {p.get('weight','?')} кг → 🎯 {p.get('target_weight','?')} кг\n"
        f"🏆 {goals.get(p.get('goal'),'?')} | 💪 {exp.get(p.get('experience'),'?')}\n"
        f"🏋️ {p.get('equipment','?')} | {p.get('days_per_week','?')} дн/нед\n"
        f"🩺 Травмы: {', '.join(p.get('injuries') or []) or 'нет'}\n\n"
        f"🔥 {round(p.get('daily_calories') or 0)} ккал/день\n"
        f"Б:{round(p.get('daily_protein') or 0)}г | "
        f"Ж:{round(p.get('daily_fat') or 0)}г | "
        f"У:{round(p.get('daily_carbs') or 0)}г",
        reply_markup=main_menu()
    )


# ─────────────────────────────────────────────
# CALLBACKS
# ─────────────────────────────────────────────

@dp.callback_query(F.data.startswith("nrg_"))
async def cb_energy(callback: CallbackQuery):
    level = int(callback.data.split("_")[1])
    user  = get_user(callback.from_user.id)
    if not user: return
    uid = user["id"]
    save_checkin(uid, {"energy_level": level})
    sleep_h = calc_sleep(uid, callback.from_user.id)

    words = {1:"Понял, бережём силы сегодня 🙏", 3:"Хорошо!", 5:"Огонь! 🔥"}
    msg = words.get(level, "Записал!")
    if sleep_h:
        msg += f"\n😴 Поспал {sleep_h} ч — {'маловато' if sleep_h<6 else 'хорошо!'}"

    await callback.message.edit_text(msg)
    await callback.message.answer(
        "Готов к тренировке или нужна лёгкая версия?" if level <= 2 else "Отличный день впереди! 💪",
        reply_markup=main_menu()
    )


# ─────────────────────────────────────────────
# SCHEDULER
# ─────────────────────────────────────────────

async def scheduler():
    days_map = {0:'mon',1:'tue',2:'wed',3:'thu',4:'fri',5:'sat',6:'sun'}
    print("⏰ Scheduler запущен")
    while True:
        try:
            now  = datetime.utcnow()
            time = now.strftime("%H:%M")
            day  = days_map[now.weekday()]

            for rem in get_due_reminders(time, day):
                try:
                    tg_id   = rem["telegram_id"]
                    user    = get_user(tg_id)
                    if not user or user.get("status")=="banned": continue
                    uid     = user["id"]
                    profile = get_profile(uid)
                    today   = {**today_food(uid), **(get_checkin(uid) or {})}
                    notes   = get_notes(uid)

                    text = await ai_reminder_text(rem["type"], profile, today, notes)

                    if rem["type"] == "morning":
                        await bot.send_message(tg_id, text, reply_markup=energy_kb())
                    else:
                        await bot.send_message(tg_id, text, reply_markup=main_menu())

                    db("reminders").update({"last_sent":datetime.utcnow().isoformat()})\
                        .eq("id",rem["id"]).execute()

                except Exception as e:
                    print(f"Reminder error: {e}")

        except Exception as e:
            print(f"Scheduler error: {e}")

        await asyncio.sleep(60)


# ─────────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────────

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    user = get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin","superadmin"]: return
    s = get_stats()
    await message.answer(
        f"👑 Админ\n\n👥 {s['total']} | ✅ {s['active']} | 📋 {s['onboarded']}\n\n"
        f"/ban [id] | /unban [id] | /broadcast [текст]"
    )

@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    user = get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin","superadmin"]: return
    args = message.text.split()
    if len(args)<2: await message.answer("/ban [id]"); return
    db("users").update({"status":"banned"}).eq("telegram_id",int(args[1])).execute()
    await message.answer(f"✅ Забанен {args[1]}")

@dp.message(Command("unban"))
async def cmd_unban(message: Message):
    user = get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin","superadmin"]: return
    args = message.text.split()
    if len(args)<2: await message.answer("/unban [id]"); return
    db("users").update({"status":"active"}).eq("telegram_id",int(args[1])).execute()
    await message.answer(f"✅ Разбанен {args[1]}")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    user = get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin","superadmin"]: return
    text = message.text.replace("/broadcast","").strip()
    if not text: await message.answer("/broadcast [текст]"); return
    users = get_all_users("active")
    sent  = 0
    for u in users:
        try:
            await bot.send_message(u["telegram_id"], text)
            sent += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Отправлено: {sent}/{len(users)}")


# ─────────────────────────────────────────────
# ЗАПУСК
# ─────────────────────────────────────────────

async def main():
    print("🤖 FitBot запущен!")
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import os, asyncio, json, re
from datetime import datetime, date, timedelta
from openai import AsyncOpenAI
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv(dotenv_path="config/.env")

bot    = Bot(token=os.getenv("TELEGRAM_TOKEN"))
dp     = Dispatcher(storage=MemoryStorage())
ai     = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL  = "gpt-4o-mini"
sb: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

# ── КЛАВИАТУРЫ ──────────────────────────────────────────────────────────────

def menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💪 Тренировка"), KeyboardButton(text="🥗 Питание")],
        [KeyboardButton(text="📊 Прогресс"),   KeyboardButton(text="📅 Расписание")],
        [KeyboardButton(text="⚙️ Профиль"),    KeyboardButton(text="💬 Спросить Макса")]
    ], resize_keyboard=True)

def energy_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="😴 Устал",  callback_data="e1"),
        InlineKeyboardButton(text="😐 Норм",   callback_data="e3"),
        InlineKeyboardButton(text="⚡ Огонь",  callback_data="e5"),
    ]])

# ── БД ──────────────────────────────────────────────────────────────────────

def q(table): return sb.table(table)

def get_user(tid):
    r = q("users").select("*").eq("telegram_id", tid).execute()
    return r.data[0] if r.data else None

def make_user(tid, uname, fname, lname=None):
    r = q("users").insert({"telegram_id":tid,"username":uname,"first_name":fname,"last_name":lname}).execute()
    return r.data[0] if r.data else None

def upd_user(tid, data):
    q("users").update(data).eq("telegram_id", tid).execute()

def get_prof(uid):
    r = q("profile").select("*").eq("user_id", uid).execute()
    return r.data[0] if r.data else {}

def upd_prof(uid, data):
    data["updated_at"] = datetime.utcnow().isoformat()
    q("profile").update(data).eq("user_id", uid).execute()

def add_msg(uid, role, text):
    q("messages").insert({"user_id":uid,"role":role,"content":text}).execute()

def get_hist(uid, n=20):
    r = q("messages").select("role,content").eq("user_id",uid).order("created_at",desc=True).limit(n).execute()
    return list(reversed(r.data or []))

def log_food(uid, desc, cal, prot, fat, carbs, approx=False):
    q("nutrition_log").insert({"user_id":uid,"food_description":desc,"calories":cal,"protein":prot,"fat":fat,"carbs":carbs,"is_approximate":approx}).execute()

def today_food(uid):
    today = date.today().isoformat()
    r = q("nutrition_log").select("*").eq("user_id",uid).gte("logged_at",f"{today}T00:00:00").execute()
    t = {"calories":0.0,"protein":0.0,"fat":0.0,"carbs":0.0}
    for i in (r.data or []):
        t["calories"]+=i.get("calories") or 0
        t["protein"] +=i.get("protein")  or 0
        t["fat"]     +=i.get("fat")      or 0
        t["carbs"]   +=i.get("carbs")    or 0
    return t

def save_plan(uid, text):
    q("workout_plans").update({"is_active":False}).eq("user_id",uid).execute()
    q("workout_plans").insert({"user_id":uid,"plan_text":text,"week_start":date.today().isoformat(),"is_active":True}).execute()

def get_plan(uid):
    r = q("workout_plans").select("*").eq("user_id",uid).eq("is_active",True).execute()
    return r.data[0] if r.data else None

def save_checkin(uid, data):
    today = date.today().isoformat()
    data.update({"user_id":uid,"date":today})
    ex = q("daily_checkins").select("id").eq("user_id",uid).eq("date",today).execute()
    if ex.data: q("daily_checkins").update(data).eq("user_id",uid).eq("date",today).execute()
    else: q("daily_checkins").insert(data).execute()

def get_checkin(uid):
    r = q("daily_checkins").select("*").eq("user_id",uid).eq("date",date.today().isoformat()).execute()
    return r.data[0] if r.data else {}

def set_sleep(tid):
    q("users").update({"sleep_time_last":datetime.utcnow().isoformat()}).eq("telegram_id",tid).execute()

def calc_sleep(uid, tid):
    r = q("users").select("sleep_time_last").eq("telegram_id",tid).execute()
    if not r.data or not r.data[0].get("sleep_time_last"): return None
    t = datetime.fromisoformat(r.data[0]["sleep_time_last"].replace("Z",""))
    h = round((datetime.utcnow()-t).seconds/3600,1)
    if 2<=h<=14:
        save_checkin(uid,{"sleep_hours":h})
        return h
    return None

def save_note(uid, key, value):
    ex = q("user_notes").select("id").eq("user_id",uid).eq("key",key).execute()
    if ex.data: q("user_notes").update({"value":value,"last_mentioned":datetime.utcnow().isoformat()}).eq("user_id",uid).eq("key",key).execute()
    else: q("user_notes").insert({"user_id":uid,"category":"auto","key":key,"value":value}).execute()

def get_notes(uid):
    r = q("user_notes").select("*").eq("user_id",uid).eq("is_active",True).execute()
    return r.data or []

def save_reminder(uid, tid, rtype, time_utc, days, message=""):
    q("reminders").insert({"user_id":uid,"telegram_id":tid,"type":rtype,"message":message,"time_of_day":time_utc,"days_of_week":days,"use_gpt":True,"is_active":True}).execute()

def get_due(cur_time, day):
    r = q("reminders").select("*").eq("is_active",True).execute()
    due = []
    for x in (r.data or []):
        if (x.get("time_of_day") or "")[:5]==cur_time and day in (x.get("days_of_week") or []):
            ls = x.get("last_sent") or ""
            if ls[:16]!=datetime.utcnow().isoformat()[:16]:
                due.append(x)
    return due

def get_all_users():
    r = q("users").select("*").eq("status","active").execute()
    return r.data or []

def get_stats():
    t=q("users").select("id",count="exact").execute()
    a=q("users").select("id",count="exact").eq("status","active").execute()
    o=q("users").select("id",count="exact").eq("onboarding_done",True).execute()
    return {"total":t.count or 0,"active":a.count or 0,"onboarded":o.count or 0}

def calc_bmr(age,gender,height,weight,activity,goal):
    bmr=10*weight+6.25*height-5*age+(5 if gender=="male" else -161)
    tdee=bmr*{1:1.2,2:1.375,3:1.55,4:1.725}.get(activity,1.375)
    cal=tdee+{"lose":-400,"gain":300}.get(goal,0)
    prot=weight*2.0; fat=cal*0.25/9; carbs=(cal-prot*4-fat*9)/4
    return {"bmr":round(bmr,1),"tdee":round(tdee,1),"daily_calories":round(cal,1),"daily_protein":round(prot,1),"daily_fat":round(fat,1),"daily_carbs":round(carbs,1)}

# ── AI ───────────────────────────────────────────────────────────────────────

PROFILE_FIELDS = {"age","gender","height","weight","target_weight","goal","experience","days_per_week","session_duration","equipment","wake_time","work_type","travel_time_gym","injuries","diet_type","food_allergies","communication_style","activity_level","timezone_offset"}
INT_F   = {"age","height","days_per_week","session_duration","activity_level","travel_time_gym","timezone_offset"}
FLOAT_F = {"weight","target_weight"}
LIST_F  = {"injuries","food_allergies"}

def convert(field, value):
    if value is None or str(value).lower() in ["null","none","не знаю","хз","?"]: return None
    if field in INT_F:
        try: return int(float(str(value)))
        except: return None
    if field in FLOAT_F:
        try: return float(str(value))
        except: return None
    if field in LIST_F:
        if isinstance(value,list): return value
        s=str(value).lower().strip().replace("[","").replace("]","")
        if s in ["нет","no","none",""]: return []
        return [v.strip() for v in s.split(",") if v.strip()]
    return value

async def ai_main(uid, user_msg, profile, today_data, notes, tz_offset=3):
    """Главный AI — отвечает живо"""
    p=profile or {}
    goals={'lose':'похудение','gain':'набор','maintain':'поддержание','health':'здоровье'}
    exp={'beginner':'новичок','intermediate':'средний','advanced':'продвинутый'}

    now_local = datetime.utcnow() + timedelta(hours=tz)
    sys = f"""Ты — Макс, личный фитнес-тренер. Живой, дружелюбный, умный.
Общаешься как человек — без скриптов и анкет. Только русский. Макс 200 слов.
Сейчас: {now_local.strftime("%H:%M %d.%m.%Y")} (местное время юзера, UTC+{tz})

ДАННЫЕ ЮЗЕРА:
Возраст:{p.get('age','?')} Пол:{'м' if p.get('gender')=='male' else 'ж' if p.get('gender')=='female' else '?'} Рост:{p.get('height','?')}см Вес:{p.get('weight','?')}кг
Цель:{goals.get(p.get('goal'),'?')} Опыт:{exp.get(p.get('experience'),'?')} Оборудование:{p.get('equipment','?')}
Травмы:{', '.join(p.get('injuries') or []) or 'нет'} Питание:{p.get('diet_type','стандарт')}
Норма:{p.get('daily_calories','?')} ккал | Б:{p.get('daily_protein','?')}г Ж:{p.get('daily_fat','?')}г У:{p.get('daily_carbs','?')}г

СЕГОДНЯ: съедено {round(today_data.get('calories',0))} ккал, белок {round(today_data.get('protein',0))}г
Сон:{today_data.get('sleep_hours','?')}ч Энергия:{today_data.get('energy_level','?')}/5

ЗАМЕТКИ: {chr(10).join([n['value'] for n in (notes or [])[:6]]) or 'нет'}

ПРАВИЛА:
- Узнавай данные юзера естественно в разговоре, по одному вопросу
- Неточные калории — пиши ~
- Медицина — "обратись к врачу"
- Травмы — не предлагай запрещённые упражнения
- Ты УМЕЕШЬ ставить напоминания"""

    hist = get_hist(uid, 20)
    msgs = [{"role":"system","content":sys}]
    msgs += [{"role":m["role"],"content":m["content"]} for m in hist]
    msgs.append({"role":"user","content":user_msg})

    r = await ai.chat.completions.create(model=MODEL,messages=msgs,max_tokens=500,temperature=0.85)
    reply = r.choices[0].message.content
    add_msg(uid,"user",user_msg)
    add_msg(uid,"assistant",reply)
    return reply

async def ai_extract(text, uid, tz_offset=3):
    """Параллельно извлекаем данные профиля и напоминания"""
    now_local = datetime.utcnow() + timedelta(hours=tz_offset)
    
    prompt = f"""Текст: "{text}"
Местное время юзера: {now_local.strftime("%H:%M")} {now_local.strftime("%d.%m.%Y")}
UTC смещение: +{tz_offset}

Верни JSON с двумя полями:

1. "profile": объект с данными профиля если юзер их упомянул, иначе null
   Поля: age, gender(male/female), height, weight, target_weight, goal(lose/gain/maintain/health), 
   experience(beginner/intermediate/advanced), equipment(home/gym/both), injuries(массив), 
   diet_type(standard/vegetarian/vegan/keto), days_per_week, session_duration, timezone_offset(число часов от UTC)

2. "reminder": объект с напоминанием если юзер просит напомнить, иначе null
   Поля: time_utc(HH:MM в UTC!), days(массив из mon/tue/wed/thu/fri/sat/sun), message(текст)
   
   Расчёт UTC времени:
   - "через 2 минуты" = {(now_local + timedelta(minutes=2)).strftime("%H:%M")} местное = {(datetime.utcnow() + timedelta(minutes=2)).strftime("%H:%M")} UTC
   - "через час" = {(datetime.utcnow() + timedelta(hours=1)).strftime("%H:%M")} UTC
   - "в 21:00" местное = {(datetime.utcnow().replace(hour=21,minute=0) - timedelta(hours=tz_offset)).strftime("%H:%M")} UTC

Только JSON, без лишнего текста."""

    try:
        r = await ai.chat.completions.create(
            model=MODEL,
            messages=[{"role":"user","content":prompt}],
            max_tokens=200, temperature=0.1
        )
        m = re.search(r'\{[\s\S]*\}', r.choices[0].message.content)
        if m: return json.loads(m.group(0))
    except: pass
    return {}

async def ai_kbju(food):
    r = await ai.chat.completions.create(
        model=MODEL,
        messages=[{"role":"system","content":"Диетолог. Только JSON."},
                  {"role":"user","content":f'КБЖУ для: "{food}". JSON: {{"calories":число,"protein":число,"fat":число,"carbs":число,"description":"текст","is_approximate":true/false}}'}],
        max_tokens=150, temperature=0.1
    )
    try:
        m = re.search(r'\{[\s\S]*\}', r.choices[0].message.content)
        if m: return json.loads(m.group(0))
    except: pass
    return None

async def ai_plan(profile):
    injuries = ', '.join(profile.get('injuries') or []) or 'нет'
    r = await ai.chat.completions.create(
        model=MODEL,
        messages=[
            {"role":"system","content":"Тренер. Учитывай травмы — критично для безопасности."},
            {"role":"user","content":f"""План тренировок на неделю:
Цель:{profile.get('goal')} Опыт:{profile.get('experience')} Дней:{profile.get('days_per_week',3)} По:{profile.get('session_duration',60)}мин
Оборудование:{profile.get('equipment')} Травмы(ИСКЛЮЧИТЬ):{injuries}

📅 ПЛАН НА НЕДЕЛЮ
День 1 — [название]:
• Упражнение — подходы×повторения
Дни отдыха: [дни]
💡 Совет: [1 предложение]"""}
        ],
        max_tokens=900, temperature=0.5
    )
    return r.choices[0].message.content

async def ai_reminder_text(rtype, profile, today):
    p=profile or {}
    ctx=f"Юзер: {p.get('age','?')}лет, цель:{p.get('goal','?')}, съел {round(today.get('calories',0))} ккал сегодня."
    texts={"morning":"Доброе утро! Мотивация и план на день. 2-3 живых предложения.","evening":"Вечерний итог. Кратко что хорошо, что завтра. 3 предложения.","workout":"Напомни о тренировке мотивирующе. 1-2 предложения.","water":"Напомни воду с юмором. 1 предложение.","custom":"Напиши напоминание от тренера Макса. 1-2 предложения."}
    r = await ai.chat.completions.create(
        model=MODEL,
        messages=[{"role":"system","content":f"Тренер Макс. {ctx}"},{"role":"user","content":texts.get(rtype,"Короткое мотивирующее.")}],
        max_tokens=150, temperature=0.9
    )
    return r.choices[0].message.content

# ── ОБРАБОТЧИКИ ──────────────────────────────────────────────────────────────

SLEEP_W = ["спокойной ночи","сплю","иду спать","ложусь","спать","ночи"]
FOOD_W  = ["съел","съела","выпил","выпила","поел","поела","перекус","завтрак","обед","ужин","скушал"]

@dp.message(CommandStart())
async def start(message: Message):
    tg=message.from_user
    user=get_user(tg.id)
    if not user:
        make_user(tg.id,tg.username,tg.first_name,tg.last_name)
        uid=get_user(tg.id)["id"]
        reply=await ai_main(uid,f"Привет! Меня зовут {tg.first_name}",{},{},[], tz_offset=3)
        await message.answer(reply,reply_markup=ReplyKeyboardRemove())
    elif user.get("status")=="banned":
        await message.answer("🚫 Заблокирован.")
    else:
        await message.answer(f"С возвращением, {tg.first_name}! 💪",reply_markup=menu())

@dp.message(F.text)
async def handle(message: Message):
    tg_id=message.from_user.id
    text=message.text.strip()
    user=get_user(tg_id)
    if not user: await start(message); return
    if user.get("status")=="banned": await message.answer("🚫 Заблокирован."); return
    upd_user(tg_id,{"last_active":datetime.utcnow().isoformat()})
    uid=user["id"]
    profile=get_prof(uid)
    tz=profile.get("timezone_offset") or 3
    today={**today_food(uid),**(get_checkin(uid) or {})}
    notes=get_notes(uid)

    # Спать
    if any(w in text.lower() for w in SLEEP_W):
        set_sleep(tg_id)
        reply=await ai_main(uid,text,profile,today,notes,tz)
        await message.answer(reply,reply_markup=menu()); return

    # Меню
    if text=="💪 Тренировка": await show_workout(message,uid,profile); return
    if text=="🥗 Питание": await message.answer("🥗 Напиши что съел — посчитаю КБЖУ!",reply_markup=menu()); return
    if text=="📊 Прогресс": await show_progress(message,uid,profile,today); return
    if text=="📅 Расписание": await show_schedule(message,uid); return
    if text=="⚙️ Профиль": await show_profile(message,user,profile); return
    if text=="💬 Спросить Макса": await message.answer("Задай любой вопрос! 💬",reply_markup=menu()); return

    # Еда
    if any(w in text.lower() for w in FOOD_W):
        await handle_food(message,uid,profile,today,text); return

    # Параллельно: AI отвечает + извлекает данные
    reply_task   = asyncio.create_task(ai_main(uid,text,profile,today,notes,tz))
    extract_task = asyncio.create_task(ai_extract(text,uid,tz))
    reply, extracted = await asyncio.gather(reply_task, extract_task)

    # Сохраняем данные профиля
    prof_data = extracted.get("profile") if extracted else None
    if prof_data and isinstance(prof_data,dict):
        to_save={}
        for field,value in prof_data.items():
            if field in PROFILE_FIELDS:
                converted=convert(field,value)
                if converted is not None:
                    to_save[field]=converted
        if to_save:
            upd_prof(uid,to_save)
            p=get_prof(uid)
            # Пересчитываем нормы если достаточно данных
            if all([p.get("age"),p.get("gender"),p.get("height"),p.get("weight"),p.get("goal")]):
                stats=calc_bmr(p["age"],p["gender"],p["height"],float(p["weight"]),p.get("activity_level") or 2,p["goal"])
                upd_prof(uid,stats)
                if not user.get("onboarding_done"):
                    upd_user(tg_id,{"onboarding_done":True})
            print(f"✅ PROFILE saved: {to_save}")

    # Сохраняем напоминание
    rem_data = extracted.get("reminder") if extracted else None
    if rem_data and isinstance(rem_data,dict) and rem_data.get("time_utc"):
        try:
            days = rem_data.get("days") or []
            if not days:
                days = ["mon","tue","wed","thu","fri","sat","sun"]
            save_reminder(uid,tg_id,"custom",
                rem_data["time_utc"],
                days,
                rem_data.get("message","Напоминание от Макса!"))
            print(f"✅ REMINDER saved: {rem_data['time_utc']} days={days}")
        except Exception as e:
            print(f"Reminder error: {e}")

    has_menu = user.get("onboarding_done") or (get_prof(uid) or {}).get("goal")
    await message.answer(reply, reply_markup=menu() if has_menu else ReplyKeyboardRemove())

# ── КНОПКИ ───────────────────────────────────────────────────────────────────

async def show_workout(message,uid,profile):
    plan=get_plan(uid)
    if plan:
        await message.answer(f"💪 Твой план:\n\n{plan['plan_text']}\n\nНапиши «новый план» для обновления.",reply_markup=menu())
    else:
        if not profile.get("goal"):
            await message.answer("Расскажи мне о своей цели — составлю план!",reply_markup=menu()); return
        await message.answer("⏳ Составляю план...")
        plan_text=await ai_plan(profile)
        save_plan(uid,plan_text)
        await message.answer(f"📅 {plan_text}",reply_markup=menu())

async def handle_food(message,uid,profile,today,text):
    await message.answer("⏳ Считаю КБЖУ...")
    n=await ai_kbju(text)
    if not n: await message.answer("Не смог посчитать. Опиши подробнее 🙏",reply_markup=menu()); return
    log_food(uid,text,n["calories"],n["protein"],n["fat"],n["carbs"],n.get("is_approximate",False))
    upd=today_food(uid)
    dc=(profile or {}).get("daily_calories") or 2000
    dp=(profile or {}).get("daily_protein") or 150
    a="~" if n.get("is_approximate") else ""
    await message.answer(
        f"✅ {n.get('description',text)}\n\n"
        f"🔥{a}{n['calories']}ккал | 🥩Б:{a}{n['protein']}г | 🥑Ж:{a}{n['fat']}г | 🍞У:{a}{n['carbs']}г\n\n"
        f"━━━━━━━━\n📈 За день: {round(upd['calories'])} / {round(dc)} ккал\n"
        f"{'✅' if dc-upd['calories']>0 else '⚠️'} Осталось: {round(dc-upd['calories'])} ккал | Белок: {round(dp-upd['protein'])}г",
        reply_markup=menu()
    )

async def show_progress(message,uid,profile,today):
    p=profile or {}
    goals={'lose':'похудение','gain':'набор','maintain':'поддержание','health':'здоровье'}
    dc=p.get("daily_calories") or 2000
    await message.answer(
        f"📊 {date.today().strftime('%d.%m.%Y')}\n\n"
        f"⚖️ {p.get('weight','?')} кг | 🎯 {goals.get(p.get('goal'),'?')}\n"
        f"😴 Сон: {today.get('sleep_hours','—')} ч | ⚡ {today.get('energy_level','—')}/5\n\n"
        f"🍽 {round(today.get('calories',0))} / {round(dc)} ккал\n"
        f"🥩 Б:{round(today.get('protein',0))}г 🥑 Ж:{round(today.get('fat',0))}г 🍞 У:{round(today.get('carbs',0))}г",
        reply_markup=menu()
    )

async def show_schedule(message,uid):
    r=sb.table("schedule").select("*").eq("user_id",uid).execute()
    if not (r.data or []):
        await message.answer("📅 Расписание не настроено.\n\nРасскажи когда просыпаешься, когда работаешь, когда удобно тренироваться — настрою!",reply_markup=menu())
    else:
        days={'mon':'Пн','tue':'Вт','wed':'Ср','thu':'Чт','fri':'Пт','sat':'Сб','sun':'Вс'}
        txt="📅 Расписание:\n\n"
        for s in r.data:
            d=days.get(s['day_of_week'],s['day_of_week'])
            txt+=f"{d}: 🌅{s.get('wake_time','?')} 💼{s.get('work_start','нет')} 💪{s.get('workout_time','?')}\n" if not s.get('is_rest_day') else f"{d}: 😴 Отдых\n"
        await message.answer(txt,reply_markup=menu())

async def show_profile(message,user,profile):
    p=profile or {}
    goals={'lose':'похудение','gain':'набор','maintain':'поддержание','health':'здоровье'}
    exp={'beginner':'новичок','intermediate':'средний','advanced':'продвинутый'}
    await message.answer(
        f"⚙️ Профиль\n\n"
        f"👤 {user.get('first_name','')} | {'♂️' if p.get('gender')=='male' else '♀️' if p.get('gender')=='female' else '?'} | {p.get('age','?')} лет\n"
        f"📏 {p.get('height','?')} см | ⚖️ {p.get('weight','?')} кг → 🎯 {p.get('target_weight','?')} кг\n"
        f"🏆 {goals.get(p.get('goal'),'?')} | 💪 {exp.get(p.get('experience'),'?')}\n"
        f"🏋️ {p.get('equipment','?')} | {p.get('days_per_week','?')} дн/нед\n"
        f"🩺 {', '.join(p.get('injuries') or []) or 'нет'}\n\n"
        f"🔥 {round(p.get('daily_calories') or 0)} ккал | Б:{round(p.get('daily_protein') or 0)} Ж:{round(p.get('daily_fat') or 0)} У:{round(p.get('daily_carbs') or 0)} г",
        reply_markup=menu()
    )

@dp.callback_query(F.data.startswith("e"))
async def cb_energy(cb: CallbackQuery):
    level=int(cb.data[1:])
    user=get_user(cb.from_user.id)
    if not user: return
    uid=user["id"]
    save_checkin(uid,{"energy_level":level})
    sleep_h=calc_sleep(uid,cb.from_user.id)
    words={1:"Понял, бережём силы 🙏",3:"Хорошо!",5:"Огонь! 🔥"}
    msg=words.get(level,"Записал!")
    if sleep_h: msg+=f"\n😴 Поспал {sleep_h} ч — {'маловато' if sleep_h<6 else 'хорошо!'}"
    await cb.message.edit_text(msg)
    await cb.message.answer("Чем займёмся?",reply_markup=menu())

# ── SCHEDULER ────────────────────────────────────────────────────────────────

async def scheduler():
    days_map={0:'mon',1:'tue',2:'wed',3:'thu',4:'fri',5:'sat',6:'sun'}
    print("⏰ Scheduler запущен")
    while True:
        try:
            now=datetime.utcnow()
            cur_time=now.strftime("%H:%M")
            cur_day=days_map[now.weekday()]
            for rem in get_due(cur_time,cur_day):
                try:
                    tg_id=rem["telegram_id"]
                    user=get_user(tg_id)
                    if not user or user.get("status")=="banned": continue
                    uid=user["id"]
                    profile=get_prof(uid)
                    today={**today_food(uid),**(get_checkin(uid) or {})}
                    rtype=rem.get("type","custom")
                    if rtype=="custom" and rem.get("message"):
                        text=f"🔔 {rem['message']}"
                    else:
                        text=await ai_reminder_text(rtype,profile,today)
                    if rtype=="morning":
                        await bot.send_message(tg_id,text,reply_markup=energy_kb())
                    else:
                        await bot.send_message(tg_id,text,reply_markup=menu())
                    sb.table("reminders").update({"last_sent":datetime.utcnow().isoformat()}).eq("id",rem["id"]).execute()
                    print(f"✅ Sent reminder to {tg_id}: {rtype}")
                except Exception as e:
                    print(f"Reminder error: {e}")
        except Exception as e:
            print(f"Scheduler error: {e}")
        await asyncio.sleep(60)

# ── ADMIN ─────────────────────────────────────────────────────────────────────

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    user=get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin","superadmin"]: return
    s=get_stats()
    await message.answer(f"👑 Админ\n👥{s['total']} ✅{s['active']} 📋{s['onboarded']}\n/ban [id] /unban [id] /broadcast [текст]")

@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    user=get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin","superadmin"]: return
    args=message.text.split()
    if len(args)<2: await message.answer("/ban [id]"); return
    sb.table("users").update({"status":"banned"}).eq("telegram_id",int(args[1])).execute()
    await message.answer(f"✅ Забанен {args[1]}")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    user=get_user(message.from_user.id)
    if not user or user.get("role") not in ["admin","superadmin"]: return
    text=message.text.replace("/broadcast","").strip()
    if not text: await message.answer("/broadcast [текст]"); return
    sent=0
    for u in get_all_users():
        try:
            await bot.send_message(u["telegram_id"],text)
            sent+=1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ {sent} отправлено")

# ── ЗАПУСК ────────────────────────────────────────────────────────────────────

async def main():
    print("🤖 FitBot запущен!")
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())

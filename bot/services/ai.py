import os
import json
import re
from datetime import datetime, timedelta
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv(dotenv_path="config/.env")

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o-mini"

# ── HELPERS ───────────────────────────────────────────────────────────────────

def _profile_str(p):
    goals = {'lose': 'похудение', 'gain': 'набор', 'maintain': 'поддержание', 'health': 'здоровье'}
    exp   = {'beginner': 'новичок', 'intermediate': 'средний', 'advanced': 'продвинутый'}
    return (
        f"Возраст:{p.get('age','?')} Пол:{'м' if p.get('gender')=='male' else 'ж' if p.get('gender')=='female' else '?'} "
        f"Рост:{p.get('height','?')}см Вес:{p.get('weight','?')}кг\n"
        f"Цель:{goals.get(p.get('goal'),'?')} Опыт:{exp.get(p.get('experience'),'?')} "
        f"Оборудование:{p.get('equipment','?')}\n"
        f"Травмы:{', '.join(p.get('injuries') or []) or 'нет'} "
        f"Питание:{p.get('diet_type','стандарт')}\n"
        f"Норма:{p.get('daily_calories','?')} ккал | "
        f"Б:{p.get('daily_protein','?')}г Ж:{p.get('daily_fat','?')}г У:{p.get('daily_carbs','?')}г"
    )

def _parse_json(text):
    try:
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return None

# ── AI MAIN (живой чат) ───────────────────────────────────────────────────────

async def ai_main(uid, user_msg, profile, today_data, notes, tz=3, system_override=None):
    from bot.db.misc import get_history, add_message
    p = profile or {}
    t = today_data or {}
    now_local = datetime.utcnow() + timedelta(hours=tz)

    system = f"""Ты — Макс, личный фитнес-тренер. Живой, дружелюбный, умный.
Общаешься как человек — без скриптов и анкет. Только русский. Макс 200 слов.
Сейчас: {now_local.strftime("%H:%M %d.%m.%Y")} (UTC+{tz})

ДАННЫЕ ЮЗЕРА:
{_profile_str(p)}

СЕГОДНЯ: съедено {round(t.get('calories', 0))} ккал, белок {round(t.get('protein', 0))}г
Сон:{t.get('sleep_hours', '?')}ч Энергия:{t.get('energy_level', '?')}/5

ЗАМЕТКИ: {chr(10).join([n['value'] for n in (notes or [])[:6]]) or 'нет'}

ПРАВИЛА:
- Узнавай данные юзера естественно, по одному вопросу
- Неточные калории — пиши ~
- Медицина — "обратись к врачу"
- Травмы — не предлагай запрещённые упражнения
- Ты умеешь ставить напоминания"""

    history = get_history(uid, 20)
    final_system = system_override if system_override else system
    msgs = [{"role": "system", "content": final_system}]
    msgs += [{"role": m["role"], "content": m["content"]} for m in history]
    msgs.append({"role": "user", "content": user_msg})

    r = await client.chat.completions.create(
        model=MODEL, messages=msgs, max_tokens=500, temperature=0.85
    )
    reply = r.choices[0].message.content
    add_message(uid, "user", user_msg)
    add_message(uid, "assistant", reply)
    return reply

# ── AI EXTRACT PROFILE ────────────────────────────────────────────────────────

async def ai_extract_profile(text):
    prompt = f"""Текст: "{text}"

Юзер упомянул данные о себе? Верни JSON или null.
JSON: {{"field": "поле", "value": "значение"}}

Поля: age(число), gender(male/female), height(число), weight(число),
target_weight(число), goal(lose/gain/maintain/health), experience(beginner/intermediate/advanced),
equipment(home/gym/both), injuries(массив), diet_type(standard/vegetarian/vegan/keto),
days_per_week(число), session_duration(число минут), timezone_offset(часов от UTC)

Только JSON или только null."""
    try:
        r = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80, temperature=0.1
        )
        raw = r.choices[0].message.content.strip()
        if raw.lower() == "null":
            return None
        return _parse_json(raw)
    except Exception:
        return None

# ── AI EXTRACT REMINDER ───────────────────────────────────────────────────────

async def ai_extract_reminder(text, tz=3):
    now_utc   = datetime.utcnow()
    now_local = now_utc + timedelta(hours=tz)
    tomorrow  = now_local + timedelta(days=1)

    prompt = f"""Текст: "{text}"
Сейчас местное: {now_local.strftime("%H:%M %d.%m.%Y")} UTC+{tz}
Завтра: {tomorrow.strftime("%d.%m.%Y")}

Юзер просит поставить напоминание? Верни JSON массив или пустой массив [].

Формат каждого напоминания:
{{
  "time_utc": "HH:MM",
  "one_time": true если разовое иначе false,
  "days": ["mon","tue","wed","thu","fri","sat","sun"] или конкретный день,
  "message": "текст напоминания (не цитата юзера — красивый текст)"
}}

Расчёт UTC (местное минус {tz}ч):
- "через 2 мин" → {(now_utc + timedelta(minutes=2)).strftime("%H:%M")} UTC, one_time:true, days:["mon","tue","wed","thu","fri","sat","sun"]
- "через час" → {(now_utc + timedelta(hours=1)).strftime("%H:%M")} UTC, one_time:true, days:["mon","tue","wed","thu","fri","sat","sun"]
- "завтра в 14:00" → {(tomorrow.replace(hour=14,minute=0) - timedelta(hours=tz)).strftime("%H:%M")} UTC, one_time:true, days:["mon","tue","wed","thu","fri","sat","sun"]
- "каждый день в 9:00" → {(now_utc.replace(hour=9,minute=0) - timedelta(hours=tz)).strftime("%H:%M")} UTC, one_time:false, days:["mon","tue","wed","thu","fri","sat","sun"]

ВАЖНО: days ВСЕГДА должен содержать названия дней недели: mon/tue/wed/thu/fri/sat/sun
НИКОГДА не пиши даты типа "2026-03-22" в days!

Если несколько напоминаний — несколько объектов в массиве.
Только JSON массив."""
    try:
        r = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200, temperature=0.1
        )
        raw = r.choices[0].message.content.strip()
        m = re.search(r'\[[\s\S]*\]', raw)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return []

# ── AI KBJU ───────────────────────────────────────────────────────────────────

async def ai_kbju(food):
    r = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Диетолог. Точные КБЖУ. Только JSON."},
            {"role": "user", "content":
             f'КБЖУ для: "{food}". JSON: {{"calories":число,"protein":число,"fat":число,"carbs":число,"description":"текст","is_approximate":true/false}}'}
        ],
        max_tokens=150, temperature=0.1
    )
    return _parse_json(r.choices[0].message.content)

# ── AI PLAN ───────────────────────────────────────────────────────────────────

async def ai_plan(profile):
    p = profile or {}
    injuries = ', '.join(p.get('injuries') or []) or 'нет'
    r = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Тренер. Учитывай травмы — критично для безопасности."},
            {"role": "user", "content":
             f"""План тренировок на неделю:
Цель:{p.get('goal')} Опыт:{p.get('experience')} Дней:{p.get('days_per_week',3)} По:{p.get('session_duration',60)}мин
Оборудование:{p.get('equipment')} Травмы(ИСКЛЮЧИТЬ):{injuries}

📅 ПЛАН НА НЕДЕЛЮ
День 1 — [название]:
• Упражнение — подходы×повторения
Дни отдыха: [дни]
💡 Совет: [1 предложение]"""}
        ],
        max_tokens=900, temperature=0.5
    )
    return r.choices[0].message.content

# ── AI REMINDER TEXT ──────────────────────────────────────────────────────────

async def ai_reminder_text(rtype, message, profile, today):
    p = profile or {}
    ctx = f"Юзер: {p.get('age','?')}лет, цель:{p.get('goal','?')}, съел {round(today.get('calories',0))} ккал."
    
    if rtype == "custom" and message:
        prompt = f"Напиши короткое живое напоминание от тренера Макса о: '{message}'. 1-2 предложения."
    else:
        prompts = {
            "morning": "Доброе утро! Мотивация и план на день. 2-3 живых предложения.",
            "evening": "Вечерний итог. Кратко что хорошо, что завтра. 3 предложения.",
            "workout": "Напомни о тренировке мотивирующе. 1-2 предложения.",
            "water":   "Напомни воду с юмором. 1 предложение.",
        }
        prompt = prompts.get(rtype, "Короткое мотивирующее. 1 предложение.")

    r = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": f"Тренер Макс. {ctx}"},
            {"role": "user", "content": prompt}
        ],
        max_tokens=150, temperature=0.9
    )
    return r.choices[0].message.content

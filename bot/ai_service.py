import os
import json
import re
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv(dotenv_path="config/.env")

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o-mini"


def build_context(profile, today, patterns, notes):
    goals_map = {'lose':'похудение','gain':'набор массы','maintain':'поддержание','health':'здоровье'}
    exp_map = {'beginner':'новичок','intermediate':'средний','advanced':'продвинутый'}
    p = profile or {}
    t = today or {}
    pat = patterns or {}
    context = f"""ПРОФИЛЬ:
- Возраст: {p.get('age','?')} лет, пол: {'м' if p.get('gender')=='male' else 'ж' if p.get('gender')=='female' else '?'}
- Рост: {p.get('height','?')} см, вес: {p.get('weight','?')} кг
- Цель: {goals_map.get(p.get('goal'),'?')}, целевой вес: {p.get('target_weight','?')} кг
- Опыт: {exp_map.get(p.get('experience'),'?')}, активность: {p.get('activity_level','?')}/4
- Оборудование: {p.get('equipment','?')}, дней/нед: {p.get('days_per_week','?')}
- Травмы: {', '.join(p.get('injuries') or []) or 'нет'}
- Питание: {p.get('diet_type','стандарт')}, аллергии: {', '.join(p.get('food_allergies') or []) or 'нет'}
- Норма: {p.get('daily_calories','?')} ккал | {p.get('daily_protein','?')}б/{p.get('daily_fat','?')}ж/{p.get('daily_carbs','?')}у г
СЕГОДНЯ:
- Калорий: {round(t.get('calories',0))} / {round(p.get('daily_calories') or 2000)} ккал
- Белок: {round(t.get('protein',0))}г
- Сон: {t.get('sleep_hours','?')} ч, энергия: {t.get('energy_level','?')}/5
ПАТТЕРНЫ:
- Выполнение плана: {pat.get('plan_adherence_percent','?')}%
- Средний сон: {pat.get('avg_sleep','?')} ч
- Стрик: {pat.get('streak_current',0)} дней"""
    if notes:
        context += "\nЗАМЕТКИ:\n" + "\n".join([f"- {n['key']}: {n['value']}" for n in notes[:10]])
    return context


def build_system_prompt(context, style='friendly'):
    styles = {'friendly':'дружелюбно и тепло','strict':'строго и по делу','humor':'с юмором и легко'}
    tone = styles.get(style,'дружелюбно')
    return f"""Ты — персональный тренер и коуч Макс. Общаешься {tone}.
Отвечаешь только на русском. Максимум 150 слов.
ПРАВИЛА:
1. Используй ТОЛЬКО данные из контекста — не придумывай цифры
2. Калории без уверенности — добавляй "~"
3. Медицина/диагнозы/лекарства — "обратись к врачу"
4. Не обещай точные результаты
5. Травмы юзера — НИКОГДА не предлагай запрещённые упражнения
{context}"""


async def extract_data(message):
    prompt = f"""Проанализируй сообщение. Только JSON.
Сообщение: "{message}"
{{"health_update":"травма/боль или null","weight_update":число или null,"mood":"настроение или null","energy":число 1-5 или null,"sleep_hours":число или null,"sleep_intent":true если идёт спать иначе false,"workout_done":true/false/null,"intent":"что хочет или null","preference":"личное предпочтение или null","custom_note":"важная инфо или null"}}"""
    try:
        r = await client.chat.completions.create(model=MODEL, messages=[{"role":"user","content":prompt}], max_tokens=200, temperature=0.1)
        match = re.search(r'\{[\s\S]*\}', r.choices[0].message.content)
        if match:
            return json.loads(match.group(0))
    except:
        pass
    return {}


async def chat(user_id, message, profile=None, today=None, patterns=None, notes=None):
    from database.db import save_message, get_chat_history
    await save_message(user_id, "user", message)
    history = await get_chat_history(user_id, limit=15)
    style = (profile or {}).get('communication_style', 'friendly')
    context = build_context(profile, today, patterns, notes)
    msgs = [{"role":"system","content":build_system_prompt(context, style)}]
    msgs += [{"role":m["role"],"content":m["content"]} for m in history]
    r = await client.chat.completions.create(model=MODEL, messages=msgs, max_tokens=400, temperature=0.7)
    reply = r.choices[0].message.content
    await save_message(user_id, "assistant", reply)
    return reply


async def calculate_nutrition(food):
    prompt = f"""КБЖУ для: "{food}". Только JSON:
{{"calories":число,"protein":число,"fat":число,"carbs":число,"description":"что посчитал","is_approximate":true/false}}"""
    try:
        r = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role":"system","content":"Диетолог. Точные КБЖУ. Только JSON."},{"role":"user","content":prompt}],
            max_tokens=150, temperature=0.1
        )
        match = re.search(r'\{[\s\S]*\}', r.choices[0].message.content)
        if match:
            return json.loads(match.group(0))
    except:
        pass
    return None


async def generate_workout_plan(profile):
    injuries = ', '.join(profile.get('injuries') or []) or 'нет'
    prompt = f"""План тренировок на неделю:
- Цель: {profile.get('goal')}, опыт: {profile.get('experience')}
- Дней: {profile.get('days_per_week',3)}, по {profile.get('session_duration',60)} мин
- Оборудование: {profile.get('equipment')}
- Травмы (ИСКЛЮЧИТЬ): {injuries}
Формат:
📅 ПЛАН НА НЕДЕЛЮ
День 1 — [название]:
- Упражнение — подходы×повторения
Дни отдыха: [дни]
💡 Совет: [1 предложение]"""
    r = await client.chat.completions.create(
        model=MODEL,
        messages=[{"role":"system","content":"Тренер. Учитывай травмы — это критично."},{"role":"user","content":prompt}],
        max_tokens=800, temperature=0.5
    )
    return r.choices[0].message.content


async def process_onboarding(step, answer):
    steps_config = {
        "ask_age":        ("age","число 10-100"),
        "ask_gender":     ("gender","male или female, определи по тексту"),
        "ask_height":     ("height","число 140-220"),
        "ask_weight":     ("weight","число 30-200"),
        "ask_target":     ("target_weight","число 30-200 или null если не знает"),
        "ask_goal":       ("goal","lose/gain/maintain/health по смыслу"),
        "ask_experience": ("experience","beginner/intermediate/advanced по смыслу"),
        "ask_days":       ("days_per_week","число 1-7"),
        "ask_duration":   ("session_duration","число минут"),
        "ask_equipment":  ("equipment","home/gym/both по смыслу"),
        "ask_wake_time":  ("wake_time","время HH:MM"),
        "ask_work":       ("work_type","sitting/active/mixed или none"),
        "ask_injuries":   ("injuries","массив строк или пустой массив []"),
        "ask_diet":       ("diet_type","standard/vegetarian/vegan/keto/other"),
        "ask_allergies":  ("food_allergies","массив строк или пустой массив []"),
        "ask_style":      ("communication_style","friendly/strict/humor"),
    }
    next_steps = {
        "ask_age":"ask_gender","ask_gender":"ask_height","ask_height":"ask_weight",
        "ask_weight":"ask_target","ask_target":"ask_goal","ask_goal":"ask_experience",
        "ask_experience":"ask_days","ask_days":"ask_duration","ask_duration":"ask_equipment",
        "ask_equipment":"ask_wake_time","ask_wake_time":"ask_work","ask_work":"ask_injuries",
        "ask_injuries":"ask_diet","ask_diet":"ask_allergies","ask_allergies":"ask_style",
        "ask_style":"completed"
    }
    field, rule = steps_config.get(step, ("unknown","любой текст"))
    prompt = f"""Шаг: {step}, поле: {field}, правило: {rule}
Ответ юзера: "{answer}"
Если подходит: {{"valid":true,"field":"{field}","value":"значение","next_state":"{next_steps.get(step,'completed')}"}}
Если нет: {{"valid":false,"reply":"короткое объяснение"}}
Только JSON."""
    try:
        r = await client.chat.completions.create(model=MODEL, messages=[{"role":"user","content":prompt}], max_tokens=100, temperature=0.1)
        match = re.search(r'\{[\s\S]*\}', r.choices[0].message.content)
        if match:
            return json.loads(match.group(0))
    except:
        pass
    return {"valid": False, "reply": "Не понял, попробуй ещё раз 😊"}


async def generate_reminder_text(rtype, profile, today, patterns):
    context = build_context(profile, today, patterns, [])
    prompts = {
        "morning":"Напиши доброе утро и главное на сегодня. 2-3 предложения.",
        "workout":"Напомни о тренировке. Учти энергию юзера. 1-2 предложения.",
        "water":"Напомни выпить воду. С юмором. 1 предложение.",
        "sleep":"Напомни готовиться ко сну. Мягко. 1 предложение.",
        "evening":"Вечерний итог. Что хорошо, что завтра. 3-4 предложения.",
    }
    r = await client.chat.completions.create(
        model=MODEL,
        messages=[{"role":"system","content":f"Тренер Макс. {context}"},{"role":"user","content":prompts.get(rtype,"Короткое мотивирующее сообщение.")}],
        max_tokens=120, temperature=0.8
    )
    return r.choices[0].message.content


def calculate_bmr_tdee(age, gender, height, weight, activity_level, goal):
    if gender == "male":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    tdee = bmr * {1:1.2,2:1.375,3:1.55,4:1.725}.get(activity_level, 1.375)
    calories = tdee + {'lose':-400,'gain':300}.get(goal, 0)
    protein = weight * 2.0
    fat = calories * 0.25 / 9
    carbs = (calories - protein * 4 - fat * 9) / 4
    return {
        "bmr":round(bmr,1),"tdee":round(tdee,1),
        "daily_calories":round(calories,1),"daily_protein":round(protein,1),
        "daily_fat":round(fat,1),"daily_carbs":round(carbs,1)
    }

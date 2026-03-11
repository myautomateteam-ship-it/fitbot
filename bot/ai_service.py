import os
from openai import AsyncOpenAI
from dotenv import load_dotenv
from database.db import get_chat_history, save_message, get_profile

load_dotenv(dotenv_path="config/.env")

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def build_system_prompt(profile: dict = None) -> str:
    base = """Ты — персональный AI фитнес-тренер по имени Макс. 
Общаешься как живой человек — дружелюбно, с юмором, по делу.
Отвечаешь только на русском языке.
Используешь эмодзи умеренно.
Помнишь всё что знаешь о пользователе и используешь это в ответах.
Никогда не говоришь что ты AI — ты тренер Макс."""

    if not profile:
        return base

    p = profile
    goals = {'lose': 'похудение', 'gain': 'набор массы', 'maintain': 'поддержание формы', 'health': 'здоровье'}
    exp = {'beginner': 'новичок', 'intermediate': 'средний', 'advanced': 'продвинутый'}
    gender_str = 'мужской' if p.get('gender') == 'male' else 'женский' if p.get('gender') == 'female' else '?'
    
    user_info = f"""

Данные пользователя:
- Возраст: {p.get('age', '?')} лет
- Пол: {gender_str}
- Рост: {p.get('height', '?')} см
- Вес: {p.get('weight', '?')} кг
- Цель: {goals.get(p.get('goal'), '?')}
- Активность: {p.get('activity_level', '?')}/4
- Опыт: {exp.get(p.get('experience'), '?')}
- Оборудование: {p.get('equipment', '?')}
- Ограничения здоровья: {p.get('health_restrictions', 'нет')}
- Предпочтения питания: {p.get('diet_preferences', 'нет')}
- Дневная норма калорий: {p.get('daily_calories', '?')} ккал
- Норма БЖУ: {p.get('daily_protein', '?')}г белка / {p.get('daily_fat', '?')}г жиров / {p.get('daily_carbs', '?')}г углеводов"""

    return base + user_info


async def chat(user_id: int, user_message: str, profile: dict = None) -> str:
    """Основной AI чат с памятью"""
    
    # Сохраняем сообщение юзера
    await save_message(user_id, "user", user_message)
    
    # Берём историю последних 15 сообщений
    history = await get_chat_history(user_id, limit=15)
    
    messages = [{"role": "system", "content": build_system_prompt(profile)}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    
    response = await client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=800,
        temperature=0.7
    )
    
    reply = response.choices[0].message.content
    
    # Сохраняем ответ бота
    await save_message(user_id, "assistant", reply)
    
    return reply


async def generate_workout_plan(profile: dict) -> str:
    """Генерация плана тренировок на неделю"""
    
    prompt = f"""Составь персональный план тренировок на неделю.

Данные пользователя:
- Возраст: {profile.get('age')} лет, пол: {'м' if profile.get('gender') == 'male' else 'ж'}
- Рост: {profile.get('height')} см, вес: {profile.get('weight')} кг
- Цель: {profile.get('goal')}
- Опыт: {profile.get('experience')}
- Оборудование: {profile.get('equipment')}
- Активность: {profile.get('activity_level')}/4
- Ограничения: {profile.get('health_restrictions') or 'нет'}
- Предпочтения: {profile.get('workout_preferences') or 'нет'}

Формат ответа:
📅 ПЛАН ТРЕНИРОВОК НА НЕДЕЛЮ

День 1 — [название]:
• Упражнение — подходы×повторения (вес/интенсивность)
...

[для каждого тренировочного дня]

Дни отдыха: [указать]

💡 Главный совет: [1 предложение под цель]"""

    response = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Ты опытный персональный тренер. Отвечай на русском."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1200,
        temperature=0.5
    )
    
    return response.choices[0].message.content


async def calculate_nutrition(food_description: str, profile: dict = None) -> dict:
    """Расчёт КБЖУ по описанию еды"""
    
    prompt = f"""Пользователь написал: "{food_description}"

Рассчитай точное КБЖУ для этой еды.
Отвечай ТОЛЬКО валидным JSON без лишнего текста:

{{
  "calories": число,
  "protein": число,
  "fat": число,
  "carbs": число,
  "description": "краткое описание что посчитал"
}}"""

    response = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Ты диетолог. Рассчитывай КБЖУ точно. Отвечай только JSON."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=200,
        temperature=0.1
    )
    
    import json, re
    raw = response.choices[0].message.content
    match = re.search(r'\{[\s\S]*\}', raw)
    if match:
        return json.loads(match.group(0))
    return None


async def process_onboarding_answer(state: str, answer: str) -> dict:
    """AI обрабатывает ответ на вопрос анкеты"""
    
    steps_map = {
        "ask_age":        ("age", "число от 10 до 100"),
        "ask_gender":     ("gender", "male или female — определи по ответу (мужской/парень/м = male, женский/девушка/ж = female)"),
        "ask_height":     ("height", "число от 100 до 250, только сантиметры"),
        "ask_weight":     ("weight", "число от 30 до 300, только килограммы"),
        "ask_goal":       ("goal", "одно из: lose (похудение), gain (набор), maintain (поддержание), health (здоровье)"),
        "ask_activity":   ("activity_level", "число 1-4: 1=сидячий, 2=лёгкая активность, 3=умеренная, 4=высокая"),
        "ask_experience": ("experience", "одно из: beginner (новичок), intermediate (средний), advanced (продвинутый)"),
        "ask_restrictions": ("health_restrictions", "текст или 'нет'"),
        "ask_equipment":  ("equipment", "одно из: home, gym, both"),
        "ask_workout_pref": ("workout_preferences", "текст или 'нет'"),
        "ask_diet":       ("diet_preferences", "текст или 'нет'"),
    }
    
    next_steps = {
        "ask_age": "ask_gender",
        "ask_gender": "ask_height",
        "ask_height": "ask_weight",
        "ask_weight": "ask_goal",
        "ask_goal": "ask_activity",
        "ask_activity": "ask_experience",
        "ask_experience": "ask_restrictions",
        "ask_restrictions": "ask_equipment",
        "ask_equipment": "ask_workout_pref",
        "ask_workout_pref": "ask_diet",
        "ask_diet": "completed",
    }
    
    next_questions = {
        "ask_gender": "⚖️ Рост? (в сантиметрах, например: 178)",
        "ask_height": "🏋️ Вес? (в килограммах, например: 75)",
        "ask_weight": "🎯 Какая главная цель?\n\n🔥 Похудеть\n💪 Набрать массу\n⚖️ Поддержать форму\n❤️ Улучшить здоровье",
        "ask_goal": "🏃 Как ты сейчас двигаешься?\n\n1️⃣ Почти не хожу пешком\n2️⃣ Лёгкая активность\n3️⃣ Тренируюсь 3-5 раз в неделю\n4️⃣ Активен каждый день",
        "ask_activity": "🌱 Опыт тренировок?\n\n🌱 Новичок — никогда серьёзно не занимался\n📈 Средний — есть опыт\n🚀 Продвинутый — тренируюсь давно",
        "ask_experience": "🩺 Есть травмы или ограничения по здоровью? (или напиши «нет»)",
        "ask_restrictions": "🏠 Где будешь тренироваться?\n\n🏠 Дома\n🏋️ В зале\n🔄 И там и там",
        "ask_equipment": "💭 Есть предпочтения в тренировках? (например: «люблю кардио», «только силовые», или «нет»)",
        "ask_workout_pref": "🥗 Есть особенности питания? (аллергии, вегетарианство, или «нет»)",
        "ask_diet": None  # completed
    }
    
    field, validation = steps_map.get(state, ("unknown", "любой текст"))
    
    prompt = f"""Шаг анкеты: {state}
Ответ пользователя: "{answer}"
Нужно извлечь поле: {field}
Правило валидации: {validation}

Если ответ подходит — верни JSON:
{{"valid": true, "field": "{field}", "value": "извлечённое_значение", "next_state": "{next_steps.get(state, 'completed')}"}}

Если не подходит — верни JSON:
{{"valid": false, "reply": "короткий дружелюбный ответ что не так и попроси повторить"}}

ТОЛЬКО JSON, никакого текста вокруг."""

    response = await client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150,
        temperature=0.1
    )
    
    import json, re
    raw = response.choices[0].message.content
    match = re.search(r'\{[\s\S]*\}', raw)
    if match:
        result = json.loads(match.group(0))
        # Добавляем следующий вопрос
        if result.get("valid") and result.get("next_state"):
            result["next_question"] = next_questions.get(state)
        return result
    
    return {"valid": False, "reply": "Не понял, попробуй ещё раз 😊"}


def calculate_bmr_tdee(age: int, gender: str, height: int, weight: float,
                        activity_level: int, goal: str) -> dict:
    """Расчёт BMR, TDEE и нормы КБЖУ"""
    
    # Формула Миффлина-Сан Жеора
    if gender == "male":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    
    activity_multipliers = {1: 1.2, 2: 1.375, 3: 1.55, 4: 1.725}
    tdee = bmr * activity_multipliers.get(activity_level, 1.375)
    
    # Корректировка под цель
    if goal == "lose":
        calories = tdee - 400
    elif goal == "gain":
        calories = tdee + 300
    else:
        calories = tdee
    
    # БЖУ
    protein = weight * 2.0
    fat = calories * 0.25 / 9
    carbs = (calories - protein * 4 - fat * 9) / 4
    
    return {
        "bmr": round(bmr, 1),
        "tdee": round(tdee, 1),
        "daily_calories": round(calories, 1),
        "daily_protein": round(protein, 1),
        "daily_fat": round(fat, 1),
        "daily_carbs": round(carbs, 1)
    }

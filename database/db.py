import os
from datetime import datetime, date, time
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv(dotenv_path="config/.env")

supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)

# =============================================
# ПОЛЬЗОВАТЕЛИ
# =============================================

async def get_user(telegram_id: int):
    res = supabase.table("users").select("*").eq("telegram_id", telegram_id).execute()
    return res.data[0] if res.data else None

async def create_user(telegram_id: int, username: str, first_name: str, last_name: str = None):
    res = supabase.table("users").insert({
        "telegram_id": telegram_id,
        "username": username,
        "first_name": first_name,
        "last_name": last_name
    }).execute()
    return res.data[0] if res.data else None

async def update_user(telegram_id: int, data: dict):
    data["last_active"] = datetime.utcnow().isoformat()
    supabase.table("users").update(data).eq("telegram_id", telegram_id).execute()

async def get_all_users(status: str = "active"):
    res = supabase.table("users").select("*").eq("status", status).execute()
    return res.data or []

async def ban_user(telegram_id: int):
    supabase.table("users").update({"status": "banned"}).eq("telegram_id", telegram_id).execute()

async def unban_user(telegram_id: int):
    supabase.table("users").update({"status": "active"}).eq("telegram_id", telegram_id).execute()

# =============================================
# ПРОФИЛЬ
# =============================================

async def get_profile(user_id: int):
    res = supabase.table("profile").select("*").eq("user_id", user_id).execute()
    return res.data[0] if res.data else None

async def update_profile(user_id: int, data: dict):
    data["updated_at"] = datetime.utcnow().isoformat()
    supabase.table("profile").update(data).eq("user_id", user_id).execute()

# =============================================
# СООБЩЕНИЯ (память AI)
# =============================================

async def save_message(user_id: int, role: str, content: str):
    supabase.table("messages").insert({
        "user_id": user_id,
        "role": role,
        "content": content
    }).execute()

async def get_chat_history(user_id: int, limit: int = 20):
    res = supabase.table("messages")\
        .select("role, content")\
        .eq("user_id", user_id)\
        .order("created_at", desc=True)\
        .limit(limit)\
        .execute()
    return list(reversed(res.data)) if res.data else []

# =============================================
# USER NOTES (свободная память)
# =============================================

async def save_note(user_id: int, category: str, key: str, value: str, source: str = None):
    # Проверяем есть ли уже такой ключ
    existing = supabase.table("user_notes")\
        .select("id")\
        .eq("user_id", user_id)\
        .eq("key", key)\
        .execute()
    
    if existing.data:
        supabase.table("user_notes").update({
            "value": value,
            "source": source,
            "last_mentioned": datetime.utcnow().isoformat()
        }).eq("user_id", user_id).eq("key", key).execute()
    else:
        supabase.table("user_notes").insert({
            "user_id": user_id,
            "category": category,
            "key": key,
            "value": value,
            "source": source
        }).execute()

async def get_notes(user_id: int):
    res = supabase.table("user_notes")\
        .select("*")\
        .eq("user_id", user_id)\
        .eq("is_active", True)\
        .execute()
    return res.data or []

# =============================================
# ПИТАНИЕ
# =============================================

async def log_nutrition(user_id: int, food: str, calories: float,
                        protein: float, fat: float, carbs: float,
                        is_approximate: bool = False):
    supabase.table("nutrition_log").insert({
        "user_id": user_id,
        "food_description": food,
        "calories": calories,
        "protein": protein,
        "fat": fat,
        "carbs": carbs,
        "is_approximate": is_approximate
    }).execute()

async def get_today_nutrition(user_id: int):
    today = date.today().isoformat()
    res = supabase.table("nutrition_log")\
        .select("*")\
        .eq("user_id", user_id)\
        .gte("logged_at", f"{today}T00:00:00")\
        .execute()
    
    total = {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0, "items": []}
    for item in (res.data or []):
        total["calories"] += item.get("calories") or 0
        total["protein"] += item.get("protein") or 0
        total["fat"] += item.get("fat") or 0
        total["carbs"] += item.get("carbs") or 0
        total["items"].append(item.get("food_description"))
    return total

# =============================================
# ТРЕНИРОВКИ
# =============================================

async def log_workout(user_id: int, workout_type: str, duration: int,
                      status: str = "done", feeling: int = None, notes: str = None):
    supabase.table("workout_log").insert({
        "user_id": user_id,
        "workout_type": workout_type,
        "duration_minutes": duration,
        "status": status,
        "feeling": feeling,
        "notes": notes
    }).execute()

async def save_workout_plan(user_id: int, plan_text: str):
    supabase.table("workout_plans").update({"is_active": False}).eq("user_id", user_id).execute()
    supabase.table("workout_plans").insert({
        "user_id": user_id,
        "plan_text": plan_text,
        "week_start": date.today().isoformat(),
        "is_active": True
    }).execute()

async def get_active_plan(user_id: int):
    res = supabase.table("workout_plans")\
        .select("*")\
        .eq("user_id", user_id)\
        .eq("is_active", True)\
        .execute()
    return res.data[0] if res.data else None

# =============================================
# ЧЕКИН
# =============================================

async def save_checkin(user_id: int, data: dict):
    today = date.today().isoformat()
    existing = supabase.table("daily_checkins")\
        .select("id")\
        .eq("user_id", user_id)\
        .eq("date", today)\
        .execute()
    
    data["user_id"] = user_id
    data["date"] = today
    
    if existing.data:
        supabase.table("daily_checkins").update(data)\
            .eq("user_id", user_id).eq("date", today).execute()
    else:
        supabase.table("daily_checkins").insert(data).execute()

async def get_today_checkin(user_id: int):
    today = date.today().isoformat()
    res = supabase.table("daily_checkins")\
        .select("*")\
        .eq("user_id", user_id)\
        .eq("date", today)\
        .execute()
    return res.data[0] if res.data else None

# =============================================
# СОН (определяем по сообщениям)
# =============================================

async def set_sleep_time(telegram_id: int):
    """Юзер написал что спит — запоминаем время"""
    supabase.table("users").update({
        "sleep_time_last": datetime.utcnow().isoformat()
    }).eq("telegram_id", telegram_id).execute()

async def calculate_sleep(user_id: int, telegram_id: int):
    """Считаем сон когда юзер написал утром"""
    user = supabase.table("users")\
        .select("sleep_time_last")\
        .eq("telegram_id", telegram_id)\
        .execute()
    
    if not user.data or not user.data[0].get("sleep_time_last"):
        return None
    
    sleep_time = datetime.fromisoformat(user.data[0]["sleep_time_last"].replace("Z", ""))
    wake_time = datetime.utcnow()
    hours = round((wake_time - sleep_time).seconds / 3600, 1)
    
    if 2 <= hours <= 14:  # адекватное время сна
        await save_checkin(user_id, {
            "sleep_hours": hours,
            "sleep_time_actual": sleep_time.strftime("%H:%M"),
            "wake_time_actual": wake_time.strftime("%H:%M")
        })
        return hours
    return None

# =============================================
# РАСПИСАНИЕ
# =============================================

async def save_schedule_day(user_id: int, day: str, data: dict):
    existing = supabase.table("schedule")\
        .select("id")\
        .eq("user_id", user_id)\
        .eq("day_of_week", day)\
        .execute()
    
    data["user_id"] = user_id
    data["day_of_week"] = day
    
    if existing.data:
        supabase.table("schedule").update(data)\
            .eq("user_id", user_id).eq("day_of_week", day).execute()
    else:
        supabase.table("schedule").insert(data).execute()

async def get_schedule(user_id: int):
    res = supabase.table("schedule").select("*").eq("user_id", user_id).execute()
    return res.data or []

async def get_schedule_day(user_id: int, day: str):
    res = supabase.table("schedule")\
        .select("*")\
        .eq("user_id", user_id)\
        .eq("day_of_week", day)\
        .execute()
    return res.data[0] if res.data else None

# =============================================
# PENDING ACTIONS (подтверждения)
# =============================================

async def create_pending(telegram_id: int, user_id: int,
                         action_type: str, action_data: dict, preview: str):
    # Удаляем старые pending для этого юзера
    supabase.table("pending_actions")\
        .delete()\
        .eq("user_id", user_id)\
        .eq("status", "pending")\
        .execute()
    
    res = supabase.table("pending_actions").insert({
        "user_id": user_id,
        "telegram_id": telegram_id,
        "action_type": action_type,
        "action_data": action_data,
        "preview_text": preview
    }).execute()
    return res.data[0] if res.data else None

async def get_pending(user_id: int):
    res = supabase.table("pending_actions")\
        .select("*")\
        .eq("user_id", user_id)\
        .eq("status", "pending")\
        .execute()
    return res.data[0] if res.data else None

async def confirm_pending(pending_id: int):
    supabase.table("pending_actions")\
        .update({"status": "confirmed"})\
        .eq("id", pending_id)\
        .execute()

async def cancel_pending(pending_id: int):
    supabase.table("pending_actions")\
        .update({"status": "cancelled"})\
        .eq("id", pending_id)\
        .execute()

# =============================================
# НАПОМИНАНИЯ
# =============================================

async def save_reminder(user_id: int, telegram_id: int, type: str,
                        message: str, time_of_day: str,
                        days: list, use_gpt: bool = False):
    supabase.table("reminders").insert({
        "user_id": user_id,
        "telegram_id": telegram_id,
        "type": type,
        "message": message,
        "time_of_day": time_of_day,
        "days_of_week": days,
        "use_gpt": use_gpt,
        "is_active": True
    }).execute()

async def get_due_reminders(current_time: str, day: str):
    """Получаем напоминания которые нужно отправить"""
    res = supabase.table("reminders")\
        .select("*")\
        .eq("is_active", True)\
        .execute()
    
    due = []
    for r in (res.data or []):
        if r.get("time_of_day") and r.get("days_of_week"):
            t = r["time_of_day"][:5]  # HH:MM
            if t == current_time and day in r["days_of_week"]:
                due.append(r)
    return due

# =============================================
# ПРОДУКТЫ И УПРАЖНЕНИЯ
# =============================================

async def search_product(name: str):
    res = supabase.table("products")\
        .select("*")\
        .ilike("name_ru", f"%{name}%")\
        .limit(5)\
        .execute()
    return res.data or []

async def search_exercise(muscle: str = None, equipment: str = None):
    query = supabase.table("exercises").select("*")
    if muscle:
        query = query.ilike("muscle_primary", f"%{muscle}%")
    if equipment:
        query = query.contains("equipment", [equipment])
    res = query.execute()
    return res.data or []

async def get_safe_exercises(injuries: list):
    """Упражнения без противопоказаний для травм юзера"""
    res = supabase.table("exercises").select("*").execute()
    safe = []
    for ex in (res.data or []):
        contraindications = ex.get("contraindications") or []
        is_safe = True
        for injury in injuries:
            for c in contraindications:
                if injury.lower() in c.lower():
                    is_safe = False
                    break
        if is_safe:
            safe.append(ex)
    return safe

# =============================================
# ПАТТЕРНЫ (пересчёт)
# =============================================

async def recalculate_patterns(user_id: int):
    """Пересчитываем паттерны юзера раз в неделю"""
    from datetime import timedelta
    
    # Последние 30 дней
    thirty_days_ago = (date.today() - timedelta(days=30)).isoformat()
    
    # Средние калории
    nutrition = supabase.table("nutrition_log")\
        .select("calories, logged_at")\
        .eq("user_id", user_id)\
        .gte("logged_at", thirty_days_ago)\
        .execute()
    
    # Тренировки
    workouts = supabase.table("workout_log")\
        .select("status, completed_at")\
        .eq("user_id", user_id)\
        .gte("completed_at", thirty_days_ago)\
        .execute()
    
    # Сон
    checkins = supabase.table("daily_checkins")\
        .select("sleep_hours, date")\
        .eq("user_id", user_id)\
        .gte("date", thirty_days_ago)\
        .execute()
    
    # Считаем
    total_cal = sum(n.get("calories") or 0 for n in (nutrition.data or []))
    days_with_food = len(set(n["logged_at"][:10] for n in (nutrition.data or [])))
    avg_cal = round(total_cal / max(days_with_food, 1), 1)
    
    sleep_values = [c.get("sleep_hours") for c in (checkins.data or []) if c.get("sleep_hours")]
    avg_sleep = round(sum(sleep_values) / len(sleep_values), 1) if sleep_values else None
    
    total_w = len(workouts.data or [])
    done_w = len([w for w in (workouts.data or []) if w.get("status") == "done"])
    adherence = round(done_w / max(total_w, 1) * 100)
    
    supabase.table("user_patterns").update({
        "avg_calories_weekday": avg_cal,
        "avg_sleep": avg_sleep,
        "plan_adherence_percent": adherence,
        "last_calculated": datetime.utcnow().isoformat()
    }).eq("user_id", user_id).execute()

# =============================================
# СТАТИСТИКА (для админки)
# =============================================

async def get_stats():
    total = supabase.table("users").select("id", count="exact").execute()
    active = supabase.table("users").select("id", count="exact").eq("status", "active").execute()
    onboarded = supabase.table("users").select("id", count="exact").eq("onboarding_done", True).execute()
    return {
        "total": total.count or 0,
        "active": active.count or 0,
        "onboarded": onboarded.count or 0
    }

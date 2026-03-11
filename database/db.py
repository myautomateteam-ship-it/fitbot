import os
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime, date

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
        "last_name": last_name,
        "last_active": datetime.utcnow().isoformat()
    }).execute()
    return res.data[0] if res.data else None

async def update_user(telegram_id: int, data: dict):
    supabase.table("users").update(data).eq("telegram_id", telegram_id).execute()

async def get_all_users(status: str = "active"):
    res = supabase.table("users").select("*").eq("status", status).execute()
    return res.data

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

async def clear_history(user_id: int):
    supabase.table("messages").delete().eq("user_id", user_id).execute()

# =============================================
# ЛОГ ПИТАНИЯ
# =============================================

async def log_nutrition(user_id: int, food: str, calories: float, protein: float, fat: float, carbs: float):
    supabase.table("nutrition_log").insert({
        "user_id": user_id,
        "food_description": food,
        "calories": calories,
        "protein": protein,
        "fat": fat,
        "carbs": carbs
    }).execute()

async def get_today_nutrition(user_id: int):
    today = date.today().isoformat()
    res = supabase.table("nutrition_log")\
        .select("*")\
        .eq("user_id", user_id)\
        .gte("logged_at", f"{today}T00:00:00")\
        .execute()
    
    total = {"calories": 0, "protein": 0, "fat": 0, "carbs": 0}
    for item in (res.data or []):
        total["calories"] += item.get("calories") or 0
        total["protein"] += item.get("protein") or 0
        total["fat"] += item.get("fat") or 0
        total["carbs"] += item.get("carbs") or 0
    return total

# =============================================
# НАПОМИНАНИЯ
# =============================================

async def create_reminder(user_id: int, telegram_id: int, type: str, message: str,
                          time_of_day: str = None, is_recurring: bool = False):
    supabase.table("reminders").insert({
        "user_id": user_id,
        "telegram_id": telegram_id,
        "type": type,
        "message": message,
        "time_of_day": time_of_day,
        "is_recurring": is_recurring,
        "is_active": True
    }).execute()

async def get_active_reminders():
    res = supabase.table("reminders").select("*").eq("is_active", True).execute()
    return res.data or []

# =============================================
# ПЛАНЫ ТРЕНИРОВОК
# =============================================

async def save_workout_plan(user_id: int, plan_text: str):
    # Деактивируем старый план
    supabase.table("workout_plans").update({"is_active": False}).eq("user_id", user_id).execute()
    # Сохраняем новый
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
# СТАТИСТИКА (для админки)
# =============================================

async def get_stats():
    total = supabase.table("users").select("id", count="exact").execute()
    active = supabase.table("users").select("id", count="exact").eq("status", "active").execute()
    banned = supabase.table("users").select("id", count="exact").eq("status", "banned").execute()
    onboarded = supabase.table("users").select("id", count="exact").eq("onboarding_done", True).execute()
    
    return {
        "total": total.count,
        "active": active.count,
        "banned": banned.count,
        "onboarded": onboarded.count
    }

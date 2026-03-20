from datetime import datetime
from bot.db.client import sb


def get_user(tid):
    r = sb.table("users").select("*").eq("telegram_id", tid).execute()
    return r.data[0] if r.data else None

def create_user(tid, username, first_name, last_name=None):
    r = sb.table("users").insert({
        "telegram_id": tid, "username": username,
        "first_name": first_name, "last_name": last_name
    }).execute()
    return r.data[0] if r.data else None

def update_user(tid, data):
    sb.table("users").update(data).eq("telegram_id", tid).execute()

def set_sleep(tid):
    sb.table("users").update({
        "sleep_time_last": datetime.utcnow().isoformat()
    }).eq("telegram_id", tid).execute()

def calc_sleep(uid, tid):
    r = sb.table("users").select("sleep_time_last").eq("telegram_id", tid).execute()
    if not r.data or not r.data[0].get("sleep_time_last"):
        return None
    t = datetime.fromisoformat(r.data[0]["sleep_time_last"].replace("Z", ""))
    h = round((datetime.utcnow() - t).seconds / 3600, 1)
    if 2 <= h <= 14:
        from bot.db.misc import save_checkin
        save_checkin(uid, {"sleep_hours": h})
        return h
    return None

def get_profile(uid):
    r = sb.table("profile").select("*").eq("user_id", uid).execute()
    return r.data[0] if r.data else {}

def update_profile(uid, data):
    data["updated_at"] = datetime.utcnow().isoformat()
    sb.table("profile").update(data).eq("user_id", uid).execute()

def get_all_users(status="active"):
    r = sb.table("users").select("*").eq("status", status).execute()
    return r.data or []

def get_stats():
    t = sb.table("users").select("id", count="exact").execute()
    a = sb.table("users").select("id", count="exact").eq("status", "active").execute()
    o = sb.table("users").select("id", count="exact").eq("onboarding_done", True).execute()
    return {"total": t.count or 0, "active": a.count or 0, "onboarded": o.count or 0}

def calc_bmr(age, gender, height, weight, activity, goal):
    bmr = 10 * weight + 6.25 * height - 5 * age + (5 if gender == "male" else -161)
    tdee = bmr * {1: 1.2, 2: 1.375, 3: 1.55, 4: 1.725}.get(activity, 1.375)
    cal = tdee + {"lose": -400, "gain": 300}.get(goal, 0)
    prot = weight * 2.0
    fat = cal * 0.25 / 9
    carbs = (cal - prot * 4 - fat * 9) / 4
    return {
        "bmr": round(bmr, 1), "tdee": round(tdee, 1),
        "daily_calories": round(cal, 1), "daily_protein": round(prot, 1),
        "daily_fat": round(fat, 1), "daily_carbs": round(carbs, 1)
    }

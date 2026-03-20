from datetime import date
from bot.db.client import sb


def log_food(uid, desc, cal, prot, fat, carbs, approx=False):
    sb.table("nutrition_log").insert({
        "user_id": uid, "food_description": desc,
        "calories": cal, "protein": prot,
        "fat": fat, "carbs": carbs,
        "is_approximate": approx
    }).execute()


def today_food(uid):
    today = date.today().isoformat()
    r = sb.table("nutrition_log").select("*") \
        .eq("user_id", uid) \
        .gte("logged_at", f"{today}T00:00:00").execute()
    t = {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
    for i in (r.data or []):
        t["calories"] += i.get("calories") or 0
        t["protein"]  += i.get("protein")  or 0
        t["fat"]      += i.get("fat")      or 0
        t["carbs"]    += i.get("carbs")    or 0
    return t

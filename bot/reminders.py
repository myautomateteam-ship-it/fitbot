from datetime import datetime
from bot.db.client import sb


def save_reminder(uid, tid, rtype, time_utc, days, message="", one_time=False):
    sb.table("reminders").insert({
        "user_id": uid, "telegram_id": tid,
        "type": rtype, "message": message,
        "time_of_day": time_utc, "days_of_week": days,
        "use_gpt": True, "is_active": True,
        "one_time": one_time
    }).execute()


def get_due_reminders(cur_time, day):
    r = sb.table("reminders").select("*").eq("is_active", True).execute()
    due = []
    for x in (r.data or []):
        if (x.get("time_of_day") or "")[:5] != cur_time:
            continue
        if day not in (x.get("days_of_week") or []):
            continue
        # Защита от дублей — не отправляем дважды в одну дату
        last = (x.get("last_sent") or "")[:10]
        today = datetime.utcnow().isoformat()[:10]
        if last == today:
            continue
        due.append(x)
    return due


def mark_sent(reminder_id, one_time=False):
    data = {"last_sent": datetime.utcnow().isoformat()}
    if one_time:
        data["is_active"] = False
    sb.table("reminders").update(data).eq("id", reminder_id).execute()


def deactivate_reminder(uid, keyword):
    """Деактивируем напоминание по ключевому слову в message"""
    r = sb.table("reminders").select("*") \
        .eq("user_id", uid).eq("is_active", True).execute()
    for rem in (r.data or []):
        msg = (rem.get("message") or "").lower()
        if keyword.lower() in msg:
            sb.table("reminders").update({"is_active": False}) \
                .eq("id", rem["id"]).execute()


def get_user_reminders(uid):
    r = sb.table("reminders").select("*") \
        .eq("user_id", uid).eq("is_active", True).execute()
    return r.data or []

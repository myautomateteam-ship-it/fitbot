from datetime import datetime, date
from bot.db.client import sb


# ── MESSAGES (память AI) ─────────────────────────────────────────────────────

def add_message(uid, role, content):
    sb.table("messages").insert({
        "user_id": uid, "role": role, "content": content
    }).execute()


def get_history(uid, limit=20):
    r = sb.table("messages").select("role,content") \
        .eq("user_id", uid) \
        .order("created_at", desc=True) \
        .limit(limit).execute()
    return list(reversed(r.data or []))


# ── USER NOTES (свободная память) ────────────────────────────────────────────

def save_note(uid, key, value, source=None):
    ex = sb.table("user_notes").select("id") \
        .eq("user_id", uid).eq("key", key).execute()
    if ex.data:
        sb.table("user_notes").update({
            "value": value, "source": source,
            "last_mentioned": datetime.utcnow().isoformat()
        }).eq("user_id", uid).eq("key", key).execute()
    else:
        sb.table("user_notes").insert({
            "user_id": uid, "category": "auto",
            "key": key, "value": value, "source": source
        }).execute()


def get_notes(uid):
    r = sb.table("user_notes").select("*") \
        .eq("user_id", uid).eq("is_active", True).execute()
    return r.data or []


# ── DAILY CHECKINS ───────────────────────────────────────────────────────────

def save_checkin(uid, data):
    today = date.today().isoformat()
    data.update({"user_id": uid, "date": today})
    ex = sb.table("daily_checkins").select("id") \
        .eq("user_id", uid).eq("date", today).execute()
    if ex.data:
        sb.table("daily_checkins").update(data) \
            .eq("user_id", uid).eq("date", today).execute()
    else:
        sb.table("daily_checkins").insert(data).execute()


def get_checkin(uid):
    r = sb.table("daily_checkins").select("*") \
        .eq("user_id", uid) \
        .eq("date", date.today().isoformat()).execute()
    return r.data[0] if r.data else {}


# ── WORKOUT PLANS ────────────────────────────────────────────────────────────

def save_plan(uid, text):
    sb.table("workout_plans").update({"is_active": False}) \
        .eq("user_id", uid).execute()
    sb.table("workout_plans").insert({
        "user_id": uid, "plan_text": text,
        "week_start": date.today().isoformat(), "is_active": True
    }).execute()


def get_plan(uid):
    r = sb.table("workout_plans").select("*") \
        .eq("user_id", uid).eq("is_active", True).execute()
    return r.data[0] if r.data else None

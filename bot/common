from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

PROFILE_FIELDS = {
    "age", "gender", "height", "weight", "target_weight",
    "goal", "experience", "days_per_week", "session_duration",
    "equipment", "injuries", "diet_type", "food_allergies",
    "activity_level", "timezone_offset"
}
INT_F   = {"age", "height", "days_per_week", "session_duration", "activity_level", "travel_time_gym", "timezone_offset"}
FLOAT_F = {"weight", "target_weight"}
LIST_F  = {"injuries", "food_allergies"}

SLEEP_WORDS = ["спокойной ночи", "сплю", "иду спать", "ложусь", "спать", "ночи"]
FOOD_WORDS  = ["съел", "съела", "выпил", "выпила", "поел", "поела",
               "перекус", "завтрак", "обед", "ужин", "скушал", "скушала"]


def main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💪 Тренировка"), KeyboardButton(text="🥗 Питание")],
        [KeyboardButton(text="📊 Прогресс"),   KeyboardButton(text="📅 Расписание")],
        [KeyboardButton(text="⚙️ Профиль"),    KeyboardButton(text="💬 Спросить Макса")]
    ], resize_keyboard=True)


def energy_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="😴 Устал",  callback_data="e_1"),
        InlineKeyboardButton(text="😐 Норм",   callback_data="e_3"),
        InlineKeyboardButton(text="⚡ Огонь",  callback_data="e_5"),
    ]])


def convert_value(field, value):
    if value is None or str(value).lower() in ["null", "none", "не знаю", "хз", "?"]:
        return None
    if field in INT_F:
        try: return int(float(str(value)))
        except: return None
    if field in FLOAT_F:
        try: return float(str(value))
        except: return None
    if field in LIST_F:
        if isinstance(value, list): return value
        s = str(value).lower().strip().replace("[", "").replace("]", "")
        if s in ["нет", "no", "none", ""]: return []
        return [v.strip() for v in s.split(",") if v.strip()]
    return value

import asyncio
from datetime import datetime
from bot.db.reminders import get_due_reminders, mark_sent
from bot.db.users import get_user, get_profile
from bot.db.nutrition import today_food
from bot.db.misc import get_checkin
from bot.services.ai import ai_reminder_text

DAYS_MAP = {0: 'mon', 1: 'tue', 2: 'wed', 3: 'thu', 4: 'fri', 5: 'sat', 6: 'sun'}


async def run_scheduler(bot, energy_kb, main_menu):
    print("⏰ Scheduler запущен")
    while True:
        try:
            now = datetime.utcnow()
            cur_time = now.strftime("%H:%M")
            cur_day  = DAYS_MAP[now.weekday()]

            for rem in get_due_reminders(cur_time, cur_day):
                try:
                    tg_id   = rem["telegram_id"]
                    user    = get_user(tg_id)
                    if not user or user.get("status") == "banned":
                        continue

                    uid     = user["id"]
                    profile = get_profile(uid)
                    today   = {**today_food(uid), **(get_checkin(uid) or {})}
                    rtype   = rem.get("type", "custom")
                    message = rem.get("message", "")
                    one_time = rem.get("one_time", False)

                    # Генерируем текст
                    text = await ai_reminder_text(rtype, message, profile, today)

                    # Отправляем
                    if rtype == "morning":
                        await bot.send_message(tg_id, text, reply_markup=energy_kb())
                    else:
                        await bot.send_message(tg_id, text, reply_markup=main_menu())

                    # Отмечаем отправленным, одноразовые деактивируем
                    mark_sent(rem["id"], one_time=one_time)
                    print(f"✅ Reminder sent [{rtype}] → {tg_id} | one_time={one_time}")

                except Exception as e:
                    print(f"❌ Reminder error {rem.get('id')}: {e}")

        except Exception as e:
            print(f"❌ Scheduler error: {e}")

        await asyncio.sleep(60)

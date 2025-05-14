from datetime import datetime, timedelta, date
from typing import Optional

import telegram
from motor.motor_asyncio import AsyncIOMotorCollection

from .bot import send_telegram_message_direct
from .config import (DAILY_BONUS_REMINDER_HOUR, CURRENCY_NAME, EMOJI_BELL, EMOJI_GIFT, EMOJI_CALENDAR, logger)

last_reminder_check_date: Optional[date] = None


async def check_and_send_daily_bonus_reminders(users_collection: AsyncIOMotorCollection, tg_bot_instance: telegram.Bot):
    global last_reminder_check_date
    now = datetime.now()
    today = now.date()

    if now.hour < DAILY_BONUS_REMINDER_HOUR or today == last_reminder_check_date:
        return

    logger.info(f"Running daily bonus reminder check for {today}...")
    try:
        three_days_ago_date = today - timedelta(days=3)

        eligible_for_reminder = users_collection.find(
            {"registered_at": {"$gte": datetime.combine(three_days_ago_date, datetime.min.time())},
                "daily_bonus_claimed_today": {"$ne": True}})

        reminder_count = 0
        async for user in eligible_for_reminder:
            chat_id = user.get("chat_id")
            registered_at = user.get("registered_at")

            if not isinstance(chat_id, int) or not registered_at:
                logger.warning(f"Worker: Skipping user with invalid data for reminder: {user.get('_id')}")
                continue

            days_since_registration = (today - registered_at.date()).days
            if 0 <= days_since_registration < 3:
                logger.info(
                    f"User {chat_id} is eligible for daily bonus reminder (Day {days_since_registration + 1}/3).")

                reminder_text = (
                    f"{EMOJI_BELL} Привет! Не забудь забрать свой <b>ежедневный бонус</b> +1 {CURRENCY_NAME} {EMOJI_GIFT}\n\n"
                    f"{EMOJI_CALENDAR} Эта возможность доступна в первые 3 дня после регистрации. Зайди в раздел 'Бонусы' в главном меню, чтобы получить!")

                success = await send_telegram_message_direct(tg_bot_instance, chat_id, reminder_text)
                if success:
                    reminder_count += 1
                else:
                    logger.warning(f"Worker: Failed to send daily bonus reminder to {chat_id}.")

        logger.info(f"Daily bonus reminder check complete. Sent {reminder_count} reminders.")
        last_reminder_check_date = today

    except Exception as reminder_err:
        logger.error(f"Worker: Error during daily bonus reminder check: {reminder_err}", exc_info=True)

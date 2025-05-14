import logging

import telegram

from .config import USER_NOTIFY_BOT_TOKEN, ADMIN_NOTIFY_BOT_TOKEN, ADMIN_CHAT_ID

logger = logging.getLogger(__name__)

user_notify_bot = None
admin_notify_bot = None


def initialize_bots():
    global user_notify_bot, admin_notify_bot
    try:
        if not USER_NOTIFY_BOT_TOKEN or len(USER_NOTIFY_BOT_TOKEN.split(':')) != 2:
            raise ValueError("Invalid USER_NOTIFY_BOT_TOKEN format.")
        user_notify_bot = telegram.Bot(token=USER_NOTIFY_BOT_TOKEN)
        logger.info("User notification Bot instance created")
    except Exception as e:
        logger.error(f"Failed to create user notification Bot instance: {e}")
        user_notify_bot = None

    try:
        if not ADMIN_NOTIFY_BOT_TOKEN or len(ADMIN_NOTIFY_BOT_TOKEN.split(':')) != 2:
            raise ValueError("Invalid ADMIN_NOTIFY_BOT_TOKEN format.")
        admin_notify_bot = telegram.Bot(token=ADMIN_NOTIFY_BOT_TOKEN)
        logger.info("Admin notification Bot instance created")
    except Exception as e:
        logger.error(f"Failed to create admin notification Bot instance: {e}")
        admin_notify_bot = None
    return user_notify_bot, admin_notify_bot


async def send_user_notification(chat_id: int, message: str, reply_markup=None):
    if not user_notify_bot:
        logger.error("User Notification Bot instance not available")
        return
    try:
        await user_notify_bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error sending USER Telegram message to {chat_id}: {e}")


async def send_admin_notification(message: str, reply_markup=None):
    if not admin_notify_bot:
        logger.error("Admin Notification Bot instance not available")
        return
    try:
        await admin_notify_bot.send_message(chat_id=str(ADMIN_CHAT_ID), text=message, reply_markup=reply_markup,
                                            parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error sending ADMIN Telegram message to {ADMIN_CHAT_ID}: {e}")

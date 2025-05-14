from typing import Optional

import telegram
from telegram import InlineKeyboardMarkup

from .config import WORKER_BOT_TOKEN, logger

tg_bot = None


def initialize_bot():
    global tg_bot
    try:
        if not WORKER_BOT_TOKEN or len(WORKER_BOT_TOKEN.split(':')) != 2:
            raise ValueError("Invalid WORKER_BOT_TOKEN format.")
        tg_bot = telegram.Bot(token=WORKER_BOT_TOKEN)
        logger.info("Telegram Bot instance created for worker.")
        return tg_bot
    except Exception as e:
        logger.error(f"Worker failed to create Telegram Bot instance: {e}")
        tg_bot = None
        raise


async def send_telegram_message_direct(bot_instance: telegram.Bot, chat_id: int, text: str,
        keyboard_markup: Optional[InlineKeyboardMarkup] = None) -> bool:
    if not bot_instance:
        logger.error("Worker Telegram bot instance not available.")
        return False
    try:
        await bot_instance.send_message(chat_id=chat_id, text=text, reply_markup=keyboard_markup, parse_mode='HTML')
        logger.info(f"Worker sent message directly to {chat_id}.")
        return True
    except telegram.error.BadRequest as e:
        if "chat not found" in str(e).lower() or "bot was blocked by the user" in str(e).lower():
            logger.warning(f"Worker: Telegram BadRequest (Chat not found/Bot blocked) sending to {chat_id}: {e}")
        else:
            logger.error(f"Worker: Telegram BadRequest sending to {chat_id}: {e}")
    except telegram.error.Forbidden as e:
        logger.warning(f"Worker: Bot blocked by user {chat_id} or chat forbidden: {e}")
    except telegram.error.NetworkError as e:
        logger.error(f"Worker: Telegram NetworkError sending to {chat_id}: {e}")
    except Exception as e:
        logger.error(f"Worker: Unexpected error sending direct message to {chat_id}: {e}")
    return False

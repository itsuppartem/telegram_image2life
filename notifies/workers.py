import asyncio
import logging
import os
from datetime import datetime, date
from typing import Optional

import telegram
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from telegram import InlineKeyboardMarkup

from .bot import initialize_bot
from .config import logger, CHECK_INTERVAL_SECONDS
from .database import connect_db, client as db_client
from .discounts import check_and_send_discount_offers
from .reminders import check_and_send_daily_bonus_reminders

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")
WORKER_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")

LOGGING_ENABLED = True
logging.basicConfig(level=logging.INFO if LOGGING_ENABLED else logging.WARNING,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BackgroundWorker")

if not all([MONGO_URI, MONGO_DB_NAME, WORKER_BOT_TOKEN]):
    logger.error("Missing required environment variables for worker")
    exit(1)

CHECK_INTERVAL_SECONDS = 60 * 15
DISCOUNT_DELAY_HOURS = 24
DAILY_BONUS_REMINDER_HOUR = 11
CURRENCY_NAME = "оживашка"
CURRENCY_NAME_PLURAL_2_4 = "оживашки"
CURRENCY_NAME_PLURAL_5_0 = "оживашек"

EMOJI_GIFT = "🎁"
EMOJI_MONEY = "💰"
EMOJI_STAR = "⭐"
EMOJI_SAD = "😔"
EMOJI_THINKING = "🤔"
EMOJI_POINT_DOWN = "👇"
EMOJI_HEART = "❤️"
EMOJI_MAGIC_WAND = "🪄"
EMOJI_CALENDAR = "📅"
EMOJI_BELL = "🔔"

client = None
db = None
users_collection = None
tg_bot = None
last_reminder_check_date: Optional[date] = None


async def connect_db():
    global client, db, users_collection
    try:
        client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        db = client[MONGO_DB_NAME]
        users_collection = db.users
        await client.admin.command('ping')
        logger.info(f"Worker successfully connected to MongoDB (DB: {MONGO_DB_NAME}).")
    except Exception as e:
        logger.error(f"Worker error connecting to MongoDB: {e}")
        raise


def initialize_bot():
    global tg_bot
    try:
        if not WORKER_BOT_TOKEN or len(WORKER_BOT_TOKEN.split(':')) != 2:
            raise ValueError("Invalid WORKER_BOT_TOKEN format.")
        tg_bot = telegram.Bot(token=WORKER_BOT_TOKEN)
        logger.info("Telegram Bot instance created for worker.")
    except Exception as e:
        logger.error(f"Worker failed to create Telegram Bot instance: {e}")
        tg_bot = None


async def send_telegram_message_direct(chat_id: int, text: str,
                                       keyboard_markup: Optional[InlineKeyboardMarkup] = None) -> bool:
    if not tg_bot:
        logger.error("Worker Telegram bot instance not available.")
        return False
    try:
        await tg_bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard_markup, parse_mode='HTML')
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


async def worker_loop():
    current_users_collection = None
    current_tg_bot = None

    try:
        current_users_collection = await connect_db()
        current_tg_bot = initialize_bot()
    except Exception:
        logger.critical("Worker: Database connection or Bot initialization failed on startup. Exiting.")
        return

    if current_users_collection is None or current_tg_bot is None:
        logger.critical("Worker: DB collection or Bot instance is None after initialization. Exiting.")
        return

    logger.info("Background worker started. Monitoring users...")

    while True:
        try:
            now = datetime.now()
            logger.debug(f"Worker loop running at {now}")

            await check_and_send_daily_bonus_reminders(current_users_collection, current_tg_bot)
            await check_and_send_discount_offers(current_users_collection, current_tg_bot)

            logger.debug(f"Worker finished checks. Sleeping for {CHECK_INTERVAL_SECONDS} seconds.")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

        except Exception as e:
            logger.error(f"Error in worker loop: {e}", exc_info=True)
            wait_time = CHECK_INTERVAL_SECONDS
            logger.info(f"Worker waiting {wait_time} seconds after error.")
            await asyncio.sleep(wait_time)


if __name__ == '__main__':
    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        logger.info("Worker stopped manually.")
    except Exception as e:
        logger.critical(f"Worker crashed outside the main loop: {e}", exc_info=True)
    finally:
        if db_client:
            db_client.close()
            logger.info("Worker MongoDB connection closed.")

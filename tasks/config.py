import logging
import os

from dotenv import load_dotenv

LOGGING_ENABLED = True
logging.basicConfig(level=logging.INFO if LOGGING_ENABLED else logging.WARNING,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")
ADMIN_NOTIFY_BOT_TOKEN = os.getenv('WORKER_BOT_TOKEN')
USER_NOTIFY_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")

if not all(
        [MONGO_URI, MONGO_DB_NAME, ADMIN_NOTIFY_BOT_TOKEN, USER_NOTIFY_BOT_TOKEN, YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY,
         ADMIN_CHAT_ID, API_URL, API_KEY]):
    logger.error("Missing required environment variables")
    exit(1)

CURRENCY_NAME = "оживашка"
CURRENCY_NAME_PLURAL_2_4 = "оживашки"
CURRENCY_NAME_PLURAL_5_0 = "оживашек"

EMOJI_PARTY = "🎉"
EMOJI_SAD = "😔"
EMOJI_CHECK = "✅"
EMOJI_CROSS = "❌"
EMOJI_WARNING = "⚠️"
EMOJI_MAGIC_WAND = "🪄"


def pluralize_ozhivashki(count: int) -> str:
    if 11 <= count % 100 <= 19:
        return CURRENCY_NAME_PLURAL_5_0
    last_digit = count % 10
    if last_digit == 1:
        return CURRENCY_NAME
    elif 2 <= last_digit <= 4:
        return CURRENCY_NAME_PLURAL_2_4
    else:
        return CURRENCY_NAME_PLURAL_5_0

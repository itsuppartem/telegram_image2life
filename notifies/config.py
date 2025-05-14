import logging
import os

from dotenv import load_dotenv

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
EMOJI_CALENDAR = "��"
EMOJI_BELL = "🔔"

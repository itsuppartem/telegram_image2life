import logging
import os

from dotenv import load_dotenv
from yookassa import Configuration as YooKassaConfig

LOGGING_ENABLED = True
logging.basicConfig(level=logging.INFO if LOGGING_ENABLED else logging.WARNING,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")
GEMINI_API_KEYS_STR = os.getenv("GEMINI_API_KEYS_STR")
API_KEY = os.getenv("API_KEY")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME")
REDIS_URL = os.getenv("REDIS_URL")

if not all([MONGO_URI, MONGO_DB_NAME, GEMINI_API_KEYS_STR, API_KEY, YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY,
            TELEGRAM_BOT_USERNAME, REDIS_URL]):
    logger.error("Отсутствуют обязательные переменные окружения. Проверьте ваш .env файл.")

GEMINI_API_KEYS = [key.strip() for key in GEMINI_API_KEYS_STR.split(',')] if GEMINI_API_KEYS_STR else []
NUM_KEYS = len(GEMINI_API_KEYS)

REQUESTS_PER_MINUTE_LIMIT = 9
REQUESTS_PER_DAY_LIMIT = 1400

GENERATION_PROMPT = ("Bring this child's drawing to life as a detailed digital painting. "
                     "Maintain the core design, whimsical elements, and composition from the original drawing, "
                     "but add believable textures, volume, dramatic lighting, and a touch of magic. "
                     "Keep the charm of the original concept but execute it in a realistic, illustrative style.")

if YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY:
    YooKassaConfig.account_id = YOOKASSA_SHOP_ID
    YooKassaConfig.secret_key = YOOKASSA_SECRET_KEY
else:
    logger.warning("YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не установлены. Платежи YooKassa будут недоступны.")

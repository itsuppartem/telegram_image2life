import logging
import os

from aiogram import Bot, Dispatcher, Router
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from dotenv import load_dotenv
from redis.asyncio import Redis

LOGGING_ENABLED = True
logging.basicConfig(level=logging.INFO if LOGGING_ENABLED else logging.WARNING,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ozhivlyator_bot")

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
API_URL = os.getenv("API_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", 'your_secret_api_key_for_internal_auth')
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not API_KEY or not API_URL or not ADMIN_CHAT_ID:
    logger.error("TELEGRAM_BOT_TOKEN, API_KEY, API_URL, and ADMIN_CHAT_ID must be set in .env")
    exit(1)

redis_client = Redis.from_url(os.getenv('REDIS_URI', 'redis://localhost:6379'))
storage = RedisStorage(redis=redis_client)
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)
router = Router()

CURRENCY_NAME = "оживашка"
CURRENCY_NAME_PLURAL_2_4 = "оживашки"
CURRENCY_NAME_PLURAL_5_0 = "оживашек"
CURRENCY_NAME_PLURAL_6_0 = "оживашку"

EMOJI_SPARKLES = "✨"
EMOJI_CAMERA = "📸"
EMOJI_MAGIC_WAND = "🪄"
EMOJI_ROBOT = "🤖"
EMOJI_GIFT = "🎁"
EMOJI_STAR = "⭐"
EMOJI_PENCIL = "✏️"
EMOJI_FRAME = "🖼️"
EMOJI_MONEY = "💰"
EMOJI_HOME = "🏡"
EMOJI_CHECK = "✅"
EMOJI_CROSS = "❌"
EMOJI_HOURGLASS = "⏳"
EMOJI_INFO = "💡"
EMOJI_WARNING = "⚠️"
EMOJI_SAD = "😔"
EMOJI_THINKING = "🤔"
EMOJI_POINT_DOWN = "👇"
EMOJI_PARTY = "🎉"
EMOJI_HEART = "❤️"
EMOJI_ARROW_LEFT = "⬅️"
EMOJI_ARROW_RIGHT = "➡️"
EMOJI_CHILD = "🧒"
EMOJI_LINK = "🔗"
EMOJI_CALENDAR = "📅"

EXAMPLE_IMAGE_PATHS = ["example_images/example1.png", "example_images/example2.png", "example_images/example3.png", ]

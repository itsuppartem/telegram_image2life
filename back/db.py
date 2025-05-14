from datetime import datetime
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient

from .config import MONGO_URI, MONGO_DB_NAME, logger

if MONGO_URI and MONGO_DB_NAME:
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    users_collection = db.users
    advertising_sources_collection = db.advertising_sources
else:
    logger.error("MONGO_URI или MONGO_DB_NAME не установлены. Функциональность базы данных будет нарушена.")
    client = None
    db = None
    users_collection = None
    advertising_sources_collection = None

redis_client = None


async def get_db_user(chat_id: int) -> Optional[dict]:
    if users_collection:
        user = await users_collection.find_one({"chat_id": chat_id})
        return user
    return None


async def update_last_activity(chat_id: int):
    if users_collection:
        await users_collection.update_one({"chat_id": chat_id}, {"$set": {"last_activity_time": datetime.now()}})

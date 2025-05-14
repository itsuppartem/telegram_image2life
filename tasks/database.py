import logging

from motor.motor_asyncio import AsyncIOMotorClient

from .config import MONGO_URI, MONGO_DB_NAME

logger = logging.getLogger(__name__)

client = None
db = None
users_collection = None


async def connect_db():
    global client, db, users_collection
    try:
        client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        db = client[MONGO_DB_NAME]
        users_collection = db.users
        await client.admin.command('ping')
        logger.info(f"Connected to MongoDB")
        return users_collection
    except Exception as e:
        logger.error(f"Error connecting to MongoDB: {e}")
        raise


async def get_users_collection():
    global users_collection
    if users_collection is None:
        await connect_db()
    return users_collection


async def close_db_connection():
    global client
    if client:
        client.close()
        logger.info("MongoDB connection closed")

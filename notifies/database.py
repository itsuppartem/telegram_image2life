from motor.motor_asyncio import AsyncIOMotorClient

from .config import MONGO_URI, MONGO_DB_NAME, logger

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
        logger.info(f"Worker successfully connected to MongoDB (DB: {MONGO_DB_NAME}).")
        return users_collection
    except Exception as e:
        logger.error(f"Worker error connecting to MongoDB: {e}")
        raise

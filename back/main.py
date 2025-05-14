from datetime import datetime

import redis.asyncio as redis_async
import uvicorn
from fastapi import FastAPI

from . import db as db_module
from .config import (REDIS_URL, NUM_KEYS, REQUESTS_PER_MINUTE_LIMIT, REQUESTS_PER_DAY_LIMIT, logger, MONGO_URI,
                     MONGO_DB_NAME, GEMINI_API_KEYS_STR, API_KEY, YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY,
                     TELEGRAM_BOT_USERNAME)
from .db import client as mongo_client
from .endpoints import router as api_router

app = FastAPI(title="Ozhivlyator Backend")


def check_env_vars():
    required_vars = {"MONGO_URI": MONGO_URI, "MONGO_DB_NAME": MONGO_DB_NAME, "GEMINI_API_KEYS_STR": GEMINI_API_KEYS_STR,
        "API_KEY": API_KEY, "YOOKASSA_SHOP_ID": YOOKASSA_SHOP_ID, "YOOKASSA_SECRET_KEY": YOOKASSA_SECRET_KEY,
        "TELEGRAM_BOT_USERNAME": TELEGRAM_BOT_USERNAME, "REDIS_URL": REDIS_URL}
    missing_vars = [name for name, value in required_vars.items() if not value]
    if missing_vars:
        logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}")
        raise RuntimeError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}")
    if NUM_KEYS == 0:
        logger.warning("GEMINI_API_KEYS_STR не содержит ключей или не задан. Генерация изображений будет невозможна.")


@app.on_event("startup")
async def startup_event():
    logger.info("Запуск Ozhivlyator Backend...")
    check_env_vars()

    if REDIS_URL:
        try:
            db_module.redis_client = redis_async.from_url(REDIS_URL, decode_responses=True)
            await db_module.redis_client.ping()
            logger.info("Успешное подключение к Redis.")
            now_ts = datetime.now().timestamp()
            for i in range(NUM_KEYS):
                key_prefix = f"gemini_key:{i}"
                await db_module.redis_client.setnx(f"{key_prefix}:minute_requests", REQUESTS_PER_MINUTE_LIMIT)
                await db_module.redis_client.setnx(f"{key_prefix}:daily_requests", REQUESTS_PER_DAY_LIMIT)
                await db_module.redis_client.setnx(f"{key_prefix}:last_minute_reset", now_ts)
                await db_module.redis_client.setnx(f"{key_prefix}:last_daily_reset", now_ts)
            logger.info("Квоты Redis инициализированы/проверены.")
        except Exception as e:
            logger.error(f"Не удалось подключиться или инициализировать Redis: {e}", exc_info=True)
            db_module.redis_client = None
    else:
        logger.warning("REDIS_URL не указан. Функциональность, зависящая от Redis, будет ограничена.")
        db_module.redis_client = None

    if mongo_client:
        try:
            await mongo_client.admin.command('ping')
            logger.info("Подключение к MongoDB успешно.")
        except Exception as e:
            logger.error(f"Ошибка подключения к MongoDB при запуске: {e}")
    else:
        logger.warning("Клиент MongoDB не инициализирован (MONGO_URI или MONGO_DB_NAME отсутствуют).")

    app.include_router(api_router)
    logger.info("Бэкенд готов.")


@app.on_event("shutdown")
async def shutdown_event():
    if db_module.redis_client:
        await db_module.redis_client.close()
        logger.info("Соединение с Redis закрыто.")
    if mongo_client:
        mongo_client.close()
        logger.info("Соединение с MongoDB закрыто.")
    logger.info("Ozhivlyator Backend завершает работу.")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, workers=4, reload=True)  # reload=True для разработки

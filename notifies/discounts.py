from datetime import datetime, timedelta

import telegram
from motor.motor_asyncio import AsyncIOMotorCollection

from .bot import send_telegram_message_direct
from .config import DISCOUNT_DELAY_HOURS, logger


async def check_and_send_discount_offers(users_collection: AsyncIOMotorCollection, tg_bot_instance: telegram.Bot):
    now = datetime.now()
    discount_threshold_time = now - timedelta(hours=DISCOUNT_DELAY_HOURS)

    try:
        eligible_for_discount = users_collection.find(
            {"generation_count": 1, "last_generation_time": {"$lt": discount_threshold_time}, "ozhivashki": 0,
                "discount_offered": {"$ne": True}})

        async for user in eligible_for_discount:
            chat_id = user.get("chat_id")
            if not isinstance(chat_id, int):
                logger.warning(f"Worker: Skipping user with invalid chat_id for discount: {chat_id}")
                continue

            logger.info(f"User {chat_id} eligible for discount offer.")

            discount_text = ("Привет! Хочу сделать тебе персональный подарок:\n"
                             "Специальная цена на пакет 10 оживашек - <s>250</s> 200 руб\n"
                             "Нажми 'Купить оживашки' в меню!")

            success = await send_telegram_message_direct(tg_bot_instance, chat_id, discount_text)

            if success:
                await users_collection.update_one({"chat_id": chat_id}, {"$set": {"discount_offered": True}})
                logger.info(f"Discount offer sent to {chat_id} and marked in DB.")
            else:
                logger.warning(f"Worker: Failed to send discount offer to {chat_id}.")
    except Exception as discount_err:
        logger.error(f"Worker: Error during discount offer check: {discount_err}", exc_info=True)

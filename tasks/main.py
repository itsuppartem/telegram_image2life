import asyncio

from .bots import initialize_bots
from .config import logger
from .database import connect_db, close_db_connection
from .payments import check_payment_status_loop


async def main():
    try:
        await connect_db()
        user_bot, admin_bot = initialize_bots()
        if not user_bot or not admin_bot:
            logger.critical("Bot initialization failed. Exiting.")
            return
        await check_payment_status_loop()
    except Exception as e:
        logger.critical(f"Main application crashed: {e}")
    finally:
        await close_db_connection()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Tasks stopped manually")
    except Exception as e:
        logger.critical(f"Tasks crashed outside the main loop: {e}")

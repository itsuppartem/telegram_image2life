import asyncio

from .config import dp, bot, router, logger


async def main():
    logger.info("Starting Ozhivlyator Bot...")
    dp.include_router(router)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    logger.info("Bot stopped.")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shutting down...")

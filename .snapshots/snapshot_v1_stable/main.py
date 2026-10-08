import os
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent
from aiohttp import web

from config import BOT_TOKEN, ADMIN_IDS
from database import init_db
from handlers import register_routers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("main")

async def start_render_health_server():
    """
    Render.com bepul Web Service portni kutadi.
    Agar PORT mavjud bo'lsa, avtomatik kichik health-server ishga tushadi.
    """
    port = int(os.getenv("PORT", 0))
    if port:
        async def handle_ping(request):
            return web.Response(text="Yukla GO Bot is Running!")

        app = web.Application()
        app.router.add_get("/", handle_ping)
        app.router.add_get("/health", handle_ping)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Render Web Server {port}-portda muvaffaqiyatli ishga tushdi.")

async def main():
    logger.info("Bot ishga tushirilmoqda...")
    
    # Ma'lumotlar bazasini tekshirish va ishga tushirish (WAL mode)
    await init_db()
    logger.info("SQLite ma'lumotlar bazasi tayyor.")

    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("XATOLIK: .env faylida BOT_TOKEN ko'rsatilmagan!")
        return

    # Render.com portini ochish (agar PORT mavjud bo'lsa)
    await start_render_health_server()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Routerlarni ulash
    register_routers(dp)

    # Global Error Handler: bot qotib qolmasligi va o'chib qolmasligi uchun
    @dp.error()
    async def error_handler(event: ErrorEvent):
        logger.error(f"Xatolik yuz berdi: {event.exception}", exc_info=True)
        return True

    logger.info(f"Adminlar ID ro'yxati: {ADMIN_IDS}")
    logger.info("Bot muvaffaqiyatli ishga tushdi va xabarlarni kutmoqda...")

    try:
        # Eski kutilgan yangilanishlarni tozalash
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Bot to'xtatildi.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")

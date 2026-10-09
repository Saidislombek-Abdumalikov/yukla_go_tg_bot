import os
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent, BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from aiohttp import web

from config import BOT_TOKEN, ADMIN_IDS
from database import init_db
from handlers import register_routers
from sheets import sheet_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("main")

async def setup_bot_commands(bot: Bot):
    try:
        # Default menu for regular users - only /start
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Botni ishga tushirish")
            ],
            scope=BotCommandScopeDefault()
        )

        # Admin menu exclusively for ADMIN_IDS
        for admin_id in ADMIN_IDS:
            await bot.set_my_commands(
                [
                    BotCommand(command="admin", description="🛠 Admin boshqaruv paneli"),
                    BotCommand(command="report", description="📸 Foto-otchyot yuborish"),
                    BotCommand(command="tolandi", description="🟢 To'lovni tasdiqlash (/tolandi YK1 YK2)"),
                    BotCommand(command="users", description="👥 Mijozlar ro'yxati"),
                    BotCommand(command="kurs", description="💵 Dollar kursini sozlash"),
                    BotCommand(command="stat", description="📊 Bot statistikasi"),
                    BotCommand(command="sync_sheets", description="📑 Google Sheets sinxronlash"),
                    BotCommand(command="backup", description="💾 Bazani yuklab olish (Backup)")
                ],
                scope=BotCommandScopeChat(chat_id=admin_id)
            )
        logger.info("Bot buyruqlar menyusi (default va admin) muvaffaqiyatli sozlandi.")
    except Exception as e:
        logger.warning(f"Buyruqlar menyusini sozlashda xatolik: {e}")

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

    # Render qayta ishga tushganda ma'lumotlar yo'qolmasligi uchun Google Sheetsdan to'liq sinxronlash
    try:
        if sheet_manager.is_configured():
            s_count = await sheet_manager.import_settings_from_sheets()
            u_count = await sheet_manager.import_all_users_to_db()
            c_count = await sheet_manager.import_all_cargos_to_db()
            if s_count > 0 or u_count > 0 or c_count > 0:
                logger.info(f"Google Sheetsdan {s_count} ta sozlama, {u_count} ta mijoz va {c_count} ta yuk hisoboti bazaga yuklandi.")
    except Exception as e:
        logger.warning(f"Google Sheets avtomatik import xatosi: {e}")

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
        # Kutilgan xabarlar o'chib ketmasligi uchun drop_pending_updates=False
        await bot.delete_webhook(drop_pending_updates=False)
        # Buyruqlar menyularini sozlash
        await setup_bot_commands(bot)
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "channel_post", "my_chat_member", "chat_member"]
        )
    finally:
        await bot.session.close()
        logger.info("Bot to'xtatildi.")

if __name__ == "__main__":
    import time
    while True:
        try:
            asyncio.run(main())
            break
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot to'xtatildi.")
            break
        except Exception as e:
            logger.error(f"Kutilmagan xatolik yuz berdi: {e}. 3 soniyadan so'ng qayta ishga tushiriladi...")
            time.sleep(3)

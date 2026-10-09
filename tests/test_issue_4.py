import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import database
from handlers.admin import cmd_mark_paid
from sheets import sheet_manager

class MockMessage:
    def __init__(self, text="", chat_id=123, message_id=456, from_user_id=123):
        self.text = text
        self.chat = MagicMock(id=chat_id)
        self.message_id = message_id
        self.from_user = MagicMock(id=from_user_id)
        self.answer = AsyncMock()

class TestIssue4PaymentFailureAndRollback(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.orig_db_path = database.DB_PATH
        database.DB_PATH = self.temp_db.name
        await database.init_db()

        self.admin_id = 999
        patcher = patch("handlers.admin.ADMIN_IDS", [self.admin_id])
        patcher.start()
        self.addCleanup(patcher.stop)

        # Mijoz va yuk yaratamiz
        async with database.get_connection() as db:
            await db.execute("""
                INSERT INTO users (user_id, username, first_name, id_code, status)
                VALUES (777, 'testclient', 'Jasur', 'YK1', 'approved')
            """)
            await db.execute("""
                INSERT INTO reports (
                    id, user_id, id_code, full_name, phone, track_codes,
                    weight, price_usd, price_uzs, payment_status, created_at
                ) VALUES (1, 777, 'YK1', 'Jasur B', '+99890', 'TRK100', 1.0, 6.0, 70000, 'qarzdor', '2026-10-09')
            """)
            await db.commit()

    async def asyncTearDown(self):
        database.DB_PATH = self.orig_db_path
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    async def test_mark_paid_fails_when_sheets_fails_no_client_notification(self):
        # 1. Sheets xato beradi (0, [])
        with patch.object(sheet_manager, "mark_cargos_paid", new=AsyncMock(return_value=(0, []))):
            bot = AsyncMock()
            msg = MockMessage(text="/tolandi YK1", from_user_id=self.admin_id)
            await cmd_mark_paid(msg, bot)

            # Mijozga (chat_id=777) xabar bormasligi kerak!
            bot.send_message.assert_not_called()

            # Bazadagi holat 'qarzdor' bo'lib qolishi kerak!
            rep = await database.get_report_by_id(1)
            self.assertEqual(rep["payment_status"], "qarzdor", "Sheets xato berganda ham SQLite bazada to'landi deb belgilandi!")

    async def test_repeated_mark_paid_does_not_resend_notification(self):
        # 2. To'lov bir marta muvaffaqiyatli o'tadi
        with patch.object(sheet_manager, "mark_cargos_paid", new=AsyncMock(return_value=(1, ["YK1"]))):
            bot = AsyncMock()
            msg = MockMessage(text="/tolandi YK1", from_user_id=self.admin_id)
            await cmd_mark_paid(msg, bot)
            self.assertEqual(bot.send_message.call_count, 1, "Mijozga birinchi to'lov xabari bormadi!")

        # Keyin yana /tolandi YK1 chaqirilganda:
        # Sheetsda endi yangilanadigan qarzdor yuk yo'q (0 ta yangilandi)
        with patch.object(sheet_manager, "mark_cargos_paid", new=AsyncMock(return_value=(0, []))):
            bot2 = AsyncMock()
            msg2 = MockMessage(text="/tolandi YK1", from_user_id=self.admin_id)
            await cmd_mark_paid(msg2, bot2)

            # Ikkinchi marta mijozga takroriy xabar ketmasligi kerak!
            bot2.send_message.assert_not_called()

if __name__ == "__main__":
    unittest.main()

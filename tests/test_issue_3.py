import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import database
from handlers.admin import state_save_new_weight, callback_del_rep_do
from sheets import sheet_manager

class MockMessage:
    def __init__(self, text="", chat_id=123, message_id=456, from_user_id=123):
        self.text = text
        self.chat = MagicMock(id=chat_id)
        self.message_id = message_id
        self.from_user = MagicMock(id=from_user_id)
        self.answer = AsyncMock()

class MockCallbackQuery:
    def __init__(self, data="", chat_id=123, message_id=456, from_user_id=123):
        self.data = data
        self.from_user = MagicMock(id=from_user_id)
        self.message = MockMessage(chat_id=chat_id, message_id=message_id, from_user_id=from_user_id)
        self.answer = AsyncMock()

class TestIssue3SheetsErrorHandling(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.orig_db_path = database.DB_PATH
        database.DB_PATH = self.temp_db.name
        await database.init_db()

        # Admin ID sozlaymiz
        self.admin_id = 999
        patcher = patch("handlers.admin.ADMIN_IDS", [self.admin_id])
        patcher.start()
        self.addCleanup(patcher.stop)

        # Test yukini bazaga kiritamiz
        async with database.get_connection() as db:
            await db.execute("""
                INSERT INTO reports (
                    id, user_id, id_code, full_name, phone, track_codes,
                    weight, price_usd, price_uzs, payment_status, created_at
                ) VALUES (1, 10, 'YK1', 'Ali V', '+99890', 'TRK1', 2.0, 12.0, 140000, 'qarzdor', '2026-10-09')
            """)
            await db.commit()

    async def asyncTearDown(self):
        database.DB_PATH = self.orig_db_path
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    async def test_weight_update_fails_gracefully_when_sheets_fails(self):
        # Sheets (False, "timeout") qaytarsin
        with patch.object(sheet_manager, "update_cargo_report", new=AsyncMock(return_value=(False, "timeout"))):
            state = AsyncMock()
            state.get_data = AsyncMock(return_value={
                "report_id": 1,
                "user_id": 10,
                "id_code": "YK1",
                "track_codes": "TRK1",
                "old_weight": 2.0
            })
            bot = AsyncMock()

            msg = MockMessage(text="5.0", from_user_id=self.admin_id)
            await state_save_new_weight(msg, state, bot)

            # 1. Muvaffaqiyat xabari ketmasligi kerak!
            sent_texts = [call.kwargs.get("text", "") or (call.args[0] if call.args else "") for call in msg.answer.call_args_list]
            all_text = " ".join(sent_texts)
            self.assertNotIn("muvaffaqiyatli yangilandi", all_text.lower(), "Sheets timeout berganda 'muvaffaqiyatli yangilandi' xabari yuborildi!")

            # 2. Bazadagi eski vazn buzilmasligi kerak (yoki qaytarilishi kerak)!
            rep = await database.get_report_by_id(1)
            self.assertEqual(rep["weight"], 2.0, f"Sheetsda xatolik bo'lsa ham lokal bazada vazn {rep['weight']} ga o'zgartirildi!")

    async def test_delete_fails_gracefully_when_sheets_fails(self):
        with patch.object(sheet_manager, "delete_cargo_report", new=AsyncMock(return_value=(False, "Google Sheets connection error"))):
            cb = MockCallbackQuery(data="del_rep_do_1_10", from_user_id=self.admin_id)
            bot = AsyncMock()
            await callback_del_rep_do(cb, bot)

            sent_texts = [call.kwargs.get("text", "") or (call.args[0] if call.args else "") for call in cb.message.answer.call_args_list]
            all_text = " ".join(sent_texts)
            self.assertNotIn("muvaffaqiyatli o'chirildi", all_text.lower(), "Sheets xato berganda 'muvaffaqiyatli o'chirildi' xabari yuborildi!")

            # Bazada yuk o'chib ketmasligi kerak!
            rep = await database.get_report_by_id(1)
            self.assertIsNotNone(rep, "Sheetsda o'chirish muvaffaqiyatsiz bo'lsa ham lokal bazadan o'chirib yuborildi!")

if __name__ == "__main__":
    unittest.main()

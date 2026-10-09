import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import database
from handlers.admin import cmd_sync_sheets
from sheets import sheet_manager

class MockMessage:
    def __init__(self, text="", chat_id=123, message_id=456, from_user_id=123):
        self.text = text
        self.chat = MagicMock(id=chat_id)
        self.message_id = message_id
        self.from_user = MagicMock(id=from_user_id)
        self.answer = AsyncMock()

class TestIssue8SyncSheetsAccuracyAndReconciliation(unittest.IsolatedAsyncioTestCase):
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

    async def asyncTearDown(self):
        database.DB_PATH = self.orig_db_path
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    async def test_sync_fails_when_import_errors_no_100_percent_success(self):
        # 1. Yuklarni import qilish xato beradi (masalan, exception yoki (False, err))
        with patch.object(sheet_manager, "is_configured", return_value=True), \
             patch.object(sheet_manager, "import_all_users_to_db", new=AsyncMock(return_value=(True, 5, "ok"))), \
             patch.object(sheet_manager, "import_all_cargos_to_db", new=AsyncMock(return_value=(False, 0, "Google API Quota Exceeded"))):

            msg = MockMessage(text="/sync_sheets", from_user_id=self.admin_id)
            await cmd_sync_sheets(msg)

            sent_texts = [call.kwargs.get("text", "") or (call.args[0] if call.args else "") for call in msg.answer.call_args_list]
            all_text = " ".join(sent_texts)

            # Agar import xato bersa, "100% mos" degan yolg'on xabar bo'lmasligi kerak!
            self.assertNotIn("100% mos", all_text, "Import xato berganda ham '100% mos' xabari berildi!")
            self.assertIn("xato", all_text.lower(), "Xatolik haqida ma'lumot berilmadi!")

if __name__ == "__main__":
    unittest.main()

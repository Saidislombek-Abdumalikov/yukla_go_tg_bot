import asyncio
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import aiosqlite

import database
from sheets import GoogleSheetManager

class MockWorksheet:
    def __init__(self, rows=None):
        self.rows = [list(r) for r in (rows or [])]

    def get_all_values(self):
        return [list(r) for r in self.rows]

    def append_row(self, row):
        self.rows.append(list(row))

class TestIssue2PhotoAndMsgIdsRestoration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.orig_db_path = database.DB_PATH
        database.DB_PATH = self.temp_db.name
        await database.init_db()

        self.sm = GoogleSheetManager()
        self.sm.is_configured = MagicMock(return_value=True)

    async def asyncTearDown(self):
        database.DB_PATH = self.orig_db_path
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    async def test_photo_and_message_ids_persisted_and_restored(self):
        ws = MockWorksheet([["Sana", "ID KOD", "Ism", "Familiya", "Telefon", "Hudud", "Trek-kod(lar)", "Og'irlik (kg)", "Kargo narxi ($)", "Kargo narxi (so'm)", "To'lov holati", "UID", "Rasm ID", "Mijoz xabar ID", "Kanal xabar ID", "Kanal chat ID"]])
        self.sm._get_cargos_worksheet_sync = MagicMock(return_value=ws)

        # 1. Yuk hisoboti saqlanadi
        cargo_data = {
            "created_at": "2026-10-09 12:00:00",
            "id_code": "YK1",
            "first_name": "Vali",
            "last_name": "Aliyev",
            "phone": "+998901234567",
            "hudud": "Toshkent",
            "track_codes": "TRK999",
            "weight": 3.5,
            "price_usd": 21.0,
            "price_uzs": 250000,
            "payment_status": "qarzdor",
            "photo_file_id": "photo_file_abc_123",
            "client_msg_id": 1001,
            "channel_msg_id": 2002,
            "channel_chat_id": "-1001234567890",
            "report_uid": "rpt_uuid_12345"
        }

        # append_cargo chaqiramiz
        ok, msg = await self.sm.append_cargo(cargo_data)
        self.assertTrue(ok)

        # Worksheetdagi qatorda rasm va xabar IDlari saqlanganini tekshiramiz
        saved_row = ws.rows[-1]
        self.assertIn("photo_file_abc_123", saved_row, "photo_file_id Google Sheetsga yozilmadi!")
        self.assertIn("1001", [str(x) for x in saved_row], "client_msg_id Google Sheetsga yozilmadi!")
        self.assertIn("2002", [str(x) for x in saved_row], "channel_msg_id Google Sheetsga yozilmadi!")
        self.assertIn("-1001234567890", [str(x) for x in saved_row], "channel_chat_id Google Sheetsga yozilmadi!")

        # 2. Yangi bo'sh bazaga import qilamiz
        new_temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        new_temp_db.close()
        database.DB_PATH = new_temp_db.name
        await database.init_db()

        try:
            imported = await self.sm.import_all_cargos_to_db()
            self.assertEqual(imported, 1)

            async with database.get_connection() as db:
                async with db.execute("SELECT photo_file_id, client_msg_id, channel_msg_id, channel_chat_id, report_uid FROM reports WHERE id_code = 'YK1'") as cur:
                    row = await cur.fetchone()
                    self.assertIsNotNone(row)
                    self.assertEqual(row[0], "photo_file_abc_123", "photo_file_id bazaga tiklanmadi!")
                    self.assertEqual(row[1], 1001, "client_msg_id bazaga tiklanmadi!")
                    self.assertEqual(row[2], 2002, "channel_msg_id bazaga tiklanmadi!")
                    self.assertEqual(row[3], "-1001234567890", "channel_chat_id bazaga tiklanmadi!")
                    self.assertEqual(row[4], "rpt_uuid_12345", "report_uid bazaga tiklanmadi!")
        finally:
            if os.path.exists(new_temp_db.name):
                os.remove(new_temp_db.name)

if __name__ == "__main__":
    unittest.main()

import asyncio
import os
import tempfile
import unittest
from unittest.mock import MagicMock

import database
from sheets import GoogleSheetManager

class MockWorksheet:
    def __init__(self, rows=None):
        self.rows = [list(r) for r in (rows or [])]

    def get_all_values(self):
        return [list(r) for r in self.rows]

    def append_row(self, row):
        self.rows.append(list(row))

    def update_cell(self, row, col, val):
        while len(self.rows) < row:
            self.rows.append([])
        while len(self.rows[row - 1]) < col:
            self.rows[row - 1].append("")
        self.rows[row - 1][col - 1] = str(val)

class TestIssue6PendingApplicationsAndSettingsPersistence(unittest.IsolatedAsyncioTestCase):
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

    async def test_pending_rejected_photos_and_settings_restored_correctly(self):
        from sheets import USER_HEADERS, SETTINGS_HEADERS
        users_ws = MockWorksheet([list(USER_HEADERS)])
        settings_ws = MockWorksheet([list(SETTINGS_HEADERS)])
        self.sm._get_users_worksheet_sync = MagicMock(return_value=users_ws)
        self.sm._get_settings_worksheet_sync = MagicMock(return_value=settings_ws)

        # 1. Yangi pending ariza topshiriladi
        user_data = {
            "username": "pending_user",
            "hudud": "Toshkent",
            "phone": "+998901112233",
            "first_name": "Sardor",
            "last_name": "Karimov",
            "passport_series": "AC1234567",
            "pinfl": "12345678901234",
            "address": "Chilonzor",
            "passport_front_id": "front_photo_id_111",
            "passport_back_id": "back_photo_id_222"
        }
        await database.save_application(111111, user_data)
        # Sheetsga ham sinxron saqlanishi kerak
        await self.sm.save_or_update_user_application(111111, user_data)

        # 2. Rejected foydalanuvchi
        rej_user = {
            "user_id": 222222,
            "username": "rejected_user",
            "hudud": "Samarqand",
            "phone": "+998902223344",
            "first_name": "Bobur",
            "last_name": "Sobirov",
            "passport_series": "AB7654321",
            "pinfl": "98765432109876",
            "address": "Registon",
            "status": "rejected"
        }
        await self.sm.save_or_update_user_application(222222, rej_user)

        # 3. Sozlamalar: dollar kursi
        await database.set_setting("usd_rate", "12900")
        await self.sm.save_setting_to_sheets("usd_rate", "12900")

        # 4. Bo'sh bazaga qayta tiklaymiz (Restore to empty DB)
        new_temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        new_temp_db.close()
        database.DB_PATH = new_temp_db.name
        await database.init_db()

        try:
            await self.sm.import_all_users_to_db()
            await self.sm.import_settings_from_sheets()

            # Tekshiruv 1: Pending foydalanuvchi tiklandimi?
            p_user = await database.get_user(111111)
            self.assertIsNotNone(p_user, "Pending foydalanuvchi yangi bazaga tiklanmadi!")
            self.assertEqual(p_user["status"], "pending", f"Pending foydalanuvchi statusi 'approved' deb tiklandi: {p_user['status']}")
            self.assertEqual(p_user["passport_front_id"], "front_photo_id_111", "Pasport front foto ID tiklanmadi!")
            self.assertEqual(p_user["passport_back_id"], "back_photo_id_222", "Pasport back foto ID tiklanmadi!")

            # Tekshiruv 2: Rejected foydalanuvchi tiklandimi?
            r_user = await database.get_user(222222)
            self.assertIsNotNone(r_user, "Rejected foydalanuvchi tiklanmadi!")
            self.assertEqual(r_user["status"], "rejected", f"Rejected foydalanuvchi noto'g'ri status bilan tiklandi: {r_user['status']}")

            # Tekshiruv 3: Sozlamalar tiklandimi?
            rate = await database.get_setting("usd_rate")
            self.assertEqual(rate, "12900", f"Sozlamalar (usd_rate) tiklanmadi: {rate}")
        finally:
            if os.path.exists(new_temp_db.name):
                os.remove(new_temp_db.name)

if __name__ == "__main__":
    unittest.main()

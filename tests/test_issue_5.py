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

class TestIssue5ReportCreationTimeAndDeduplication(unittest.IsolatedAsyncioTestCase):
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

    async def test_created_at_consistency_and_report_uid_deduplication(self):
        # 1. database.save_report ga aniq created_at beramiz
        explicit_time = "2026-10-09 10:00:00"
        report_data = {
            "user_id": 1,
            "id_code": "YK1",
            "full_name": "Test User",
            "phone": "+99890",
            "track_codes": "TRK_DIFF_SEC",
            "weight": 2.0,
            "price_usd": 12.0,
            "price_uzs": 140000,
            "created_at": explicit_time,
            "report_uid": "uid_fixed_123"
        }

        # DB ga yozamiz
        rep_id = await database.save_report(report_data)

        # DB dagi created_at ni tekshiramiz
        rep = await database.get_report_by_id(rep_id)
        self.assertEqual(rep["created_at"], explicit_time, f"database.save_report uzatilgan created_at ({explicit_time}) o'rniga boshqa vaqt yozdi: {rep['created_at']}")

        # 2. Sheetsdagi vaqt va DB dagi vaqt orasida 1 soniya farq bo'lsin:
        # Masalan Sheetsda 10:00:00 yozilgan, lekin eski kodda DB ga 10:00:01 yozilib qolgan bo'lsa
        ws = MockWorksheet([
            ["Sana", "ID KOD", "Ism", "Familiya", "Tel", "Hudud", "Trek-kod(lar)", "Og'irlik (kg)", "Narx $", "Narx so'm", "To'lov", "UID"],
            ["2026-10-09 10:00:00", "YK1", "Test", "User", "+99890", "Toshkent", "TRK_DIFF_SEC", "2.0", "12$", "140000 so'm", "Qarzdor", "uid_fixed_123"]
        ])
        self.sm._get_cargos_worksheet_sync = MagicMock(return_value=ws)

        # Import qilamiz
        await self.sm.import_all_cargos_to_db()

        # Reports soni aniq 1 ta bo'lishi kerak! Dublikat bo'lmasligi kerak!
        async with database.get_connection() as db:
            async with db.execute("SELECT count(*) FROM reports WHERE id_code = 'YK1'") as cur:
                count = (await cur.fetchone())[0]
                self.assertEqual(count, 1, f"Bitta yuk 2 marta import qilindi (dublikat hosil bo'ldi! count={count})")

if __name__ == "__main__":
    unittest.main()

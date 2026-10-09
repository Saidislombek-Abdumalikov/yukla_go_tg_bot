import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import database
from sheets import GoogleSheetManager, CARGO_HEADERS, USER_HEADERS, SETTINGS_HEADERS

class MockWorksheet:
    def __init__(self, rows=None):
        self.rows = [list(r) for r in (rows or [])]

    def get_all_values(self):
        return [list(r) for r in self.rows]

    def update_cell(self, row, col, val):
        while len(self.rows) < row:
            self.rows.append([])
        while len(self.rows[row - 1]) < col:
            self.rows[row - 1].append("")
        self.rows[row - 1][col - 1] = str(val)

    def delete_rows(self, row):
        del self.rows[row - 1]

class TestVerificationAudit(unittest.IsolatedAsyncioTestCase):
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

    async def test_main_startup_invokes_settings_users_and_cargos_restoration(self):
        """1-tekshiruv: main.py ishga tushganda sozlamalar, mijozlar va yuklar tiklanadimi?"""
        import main
        with patch.object(main.sheet_manager, "is_configured", return_value=True), \
             patch.object(main.sheet_manager, "import_settings_from_sheets", new=AsyncMock(return_value=2)) as mock_settings, \
             patch.object(main.sheet_manager, "import_all_users_to_db", new=AsyncMock(return_value=3)) as mock_users, \
             patch.object(main.sheet_manager, "import_all_cargos_to_db", new=AsyncMock(return_value=5)) as mock_cargos, \
             patch("main.init_db", new=AsyncMock()), \
             patch("main.BOT_TOKEN", "valid_token"), \
             patch("main.start_render_health_server", new=AsyncMock()), \
             patch("main.setup_bot_commands", new=AsyncMock()), \
             patch("main.Bot") as mock_bot_cls, \
             patch("main.Dispatcher") as mock_dp_cls:

            mock_bot = AsyncMock()
            mock_bot_cls.return_value = mock_bot
            mock_dp = MagicMock()
            mock_dp.start_polling = AsyncMock()
            mock_dp_cls.return_value = mock_dp

            # main() ni ishga tushiramiz (pollingni to'xtatamiz)
            mock_dp.start_polling.side_effect = asyncio.CancelledError()
            try:
                await main.main()
            except asyncio.CancelledError:
                pass

            mock_settings.assert_awaited_once()
            mock_users.assert_awaited_once()
            mock_cargos.assert_awaited_once()

    async def test_import_does_not_wipe_out_local_cargos_on_partial_or_missing_uids(self):
        """2-tekshiruv: Sheets importi lokal bazadagi mavjud yuklarni o'chirib yubormasligi kerak!"""
        # Bazada mavjud yuk bor
        await database.save_report({
            "id_code": "YK1",
            "track_codes": "LOCAL_TRACK",
            "weight": 2.0,
            "price_usd": 12.0,
            "price_uzs": 140000,
            "report_uid": "rpt_local_123"
        })

        # Sheetsda esa boshqa bitta yuk bor (masalan, tarmoq faqat bitta yukni qaytardi yoki eski yuk)
        ws = MockWorksheet([
            list(CARGO_HEADERS),
            ["2026-10-09", "YK1", "Ali", "V", "+99890", "Toshkent", "SHEET_TRACK", "1.0", "6$", "70000 so'm", "Qarzdor", "rpt_sheet_456", "", "", "", ""]
        ])
        self.sm._get_cargos_worksheet_sync = MagicMock(return_value=ws)

        await self.sm.import_all_cargos_to_db()

        # Lokal bazadagi rpt_local_123 O'CHIB KETMASLIGI KERAK!
        local_rep = await database.get_report_by_uid("rpt_local_123")
        self.assertIsNotNone(local_rep, "XAVF! Sheets importida lokal bazadagi yuk o'chirib yuborildi!")

    async def test_ambiguous_duplicate_tracks_without_uid_aborts_without_guessing(self):
        """3-tekshiruv: Bir mijozda bir xil trekli ikkita UIDsiz yozuv bo'lsa, bot taxmin qilmay amalni to'xtatishi kerak!"""
        ws = MockWorksheet([
            list(CARGO_HEADERS),
            # YK1 uchun bir xil trek 'SAME_TRK', ikkalasida ham UID yo'q (eski yozuvlar)
            ["2026-10-09", "YK1", "Ali", "V", "+99890", "Toshkent", "SAME_TRK", "1.0", "6$", "70000 so'm", "Qarzdor", "", "", "", "", ""],
            ["2026-10-09", "YK1", "Ali", "V", "+99890", "Toshkent", "SAME_TRK", "2.0", "12$", "140000 so'm", "Qarzdor", "", "", "", "", ""]
        ])
        self.sm._get_cargos_worksheet_sync = MagicMock(return_value=ws)

        # Update urinishi
        ok, msg = await self.sm.update_cargo_report(
            id_code="YK1",
            old_track_codes="SAME_TRK",
            new_weight=5.0
        )
        self.assertFalse(ok, "Bir nechta moslik bo'lganda update False qaytarishi kerak (taxmin qilmaslik kerak)!")
        self.assertIn("noaniq", msg.lower(), "Xatolik xabarida noaniqlik ko'rsatilmadi!")

        # Delete urinishi
        del_ok, del_msg = await self.sm.delete_cargo_report(
            id_code="YK1",
            track_codes="SAME_TRK"
        )
        self.assertFalse(del_ok, "Bir nechta moslik bo'lganda delete False qaytarishi kerak (taxmin qilmaslik kerak)!")
        self.assertIn("noaniq", del_msg.lower(), "Xatolik xabarida noaniqlik ko'rsatilmadi!")
        # Ikkala qator ham o'chmasdan saqlanib qolishi kerak!
        self.assertEqual(len(ws.rows), 3, "Noaniq moslikda qatorlardan biri ko'r-ko'rona o'chirib yuborildi!")

if __name__ == "__main__":
    unittest.main()

import asyncio
import unittest
from unittest.mock import MagicMock, patch
from sheets import GoogleSheetManager

class MockWorksheet:
    def __init__(self, rows):
        self.rows = [list(r) for r in rows]

    def get_all_values(self):
        return [list(r) for r in self.rows]

    def update_cell(self, row, col, val):
        self.rows[row - 1][col - 1] = str(val)

    def delete_rows(self, row):
        del self.rows[row - 1]

class TestIssue1SubstringsAndFallback(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sm = GoogleSheetManager()
        self.sm.is_configured = MagicMock(return_value=True)

    async def test_update_cargo_does_not_affect_substring_tracks_or_fallback(self):
        # Qatorlar:
        # Header
        # Qator 2: YK1, track="ABC123", weight=2.0
        # Qator 3: YK1, track="ABC12", weight=1.0
        rows = [
            ["Sana", "ID KOD", "Ism", "Familiya", "Tel", "Hudud", "Trek-kod(lar)", "Og'irlik (kg)", "Narx $", "Narx so'm", "To'lov"],
            ["2026-10-09", "YK1", "Ali", "Valiyev", "+99890", "Toshkent", "ABC123", "2.0", "12$", "140000 so'm", "Qarzdor"],
            ["2026-10-09", "YK1", "Ali", "Valiyev", "+99890", "Toshkent", "ABC12", "1.0", "6$", "70000 so'm", "Qarzdor"]
        ]
        ws = MockWorksheet(rows)
        self.sm._get_cargos_worksheet_sync = MagicMock(return_value=ws)

        # 1. ABC12 ni yangilash ABC123 ga ta'sir qilmasligi kerak
        # Agar biz ABC12 ning og'irligini 5.0 qilsak:
        # Yangi kodda report_uid orqali topilishi kerak.
        # Lekin eski kodda old_track_codes="ABC12" tekshirilganda yoki teskari qidirilganda:
        # Qator 3 (ABC12) yangilanishi kerak, Qator 2 (ABC123) esa 2.0 bo'lib qolishi kerak.
        # Ammo agar ABC123 pastda bo'lsa (yoki pastdan yuqoriga qidirilganda ABC12 in ABC123 mos kelib qolsa):
        ws2 = MockWorksheet([
            ["Sana", "ID KOD", "Ism", "Familiya", "Tel", "Hudud", "Trek-kod(lar)", "Og'irlik (kg)", "Narx $", "Narx so'm", "To'lov"],
            ["2026-10-09", "YK1", "Ali", "Valiyev", "+99890", "Toshkent", "ABC12", "1.0", "6$", "70000 so'm", "Qarzdor"],
            ["2026-10-09", "YK1", "Ali", "Valiyev", "+99890", "Toshkent", "ABC123", "2.0", "12$", "140000 so'm", "Qarzdor"]
        ])
        self.sm._get_cargos_worksheet_sync = MagicMock(return_value=ws2)

        # ABC12 ni tahrirlamoqchimiz, lekin eski kod pastdan (len-1) qidirgani uchun
        # ABC123 qatoriga kelganda "ABC12 in ABC123" bo'lib, ABC123 ning vaznini o'zgartirib yuboradi!
        ok, msg = await self.sm.update_cargo_report(
            id_code="YK1",
            old_track_codes="ABC12",
            new_weight=9.9
        )
        self.assertTrue(ok)
        # ABC123 ning vazni 2.0 ligicha qolishi shart! ABC12 esa 9.9 bo'lishi kerak!
        self.assertEqual(ws2.rows[2][7], "2.0", "ABC123 xato tahrirlandi, chunki substring tekshiruvi ABC12 ni ABC123 ga mos deb topdi!")
        self.assertEqual(ws2.rows[1][7], "9.9", "Haqiqiy ABC12 qatori tahrirlanmadi!")

    async def test_fallback_to_last_row_is_prevented(self):
        # Mavjud bo'lmagan trek berilganda hech qaysi qator o'zgarmasligi kerak!
        rows = [
            ["Sana", "ID KOD", "Ism", "Familiya", "Tel", "Hudud", "Trek-kod(lar)", "Og'irlik (kg)", "Narx $", "Narx so'm", "To'lov"],
            ["2026-10-09", "YK1", "Ali", "Valiyev", "+99890", "Toshkent", "EXISTING_TRACK", "1.0", "6$", "70000 so'm", "Qarzdor"]
        ]
        ws = MockWorksheet(rows)
        self.sm._get_cargos_worksheet_sync = MagicMock(return_value=ws)

        ok, msg = await self.sm.update_cargo_report(
            id_code="YK1",
            old_track_codes="NON_EXISTENT_TRACK",
            new_weight=99.0
        )
        # Yangi kodda ok False bo'lishi yoki mavjud qator o'zgarmasligi shart!
        self.assertFalse(ok, "Mavjud bo'lmagan trek uchun update False qaytarishi kerak!")
        self.assertEqual(ws.rows[1][7], "1.0", "Mavjud bo'lmagan trek fallback orqali oxirgi qatorni o'zgartirib yubordi!")

    async def test_delete_fallback_to_last_row_is_prevented(self):
        rows = [
            ["Sana", "ID KOD", "Ism", "Familiya", "Tel", "Hudud", "Trek-kod(lar)", "Og'irlik (kg)", "Narx $", "Narx so'm", "To'lov"],
            ["2026-10-09", "YK1", "Ali", "Valiyev", "+99890", "Toshkent", "MY_CARGO", "1.0", "6$", "70000 so'm", "Qarzdor"]
        ]
        ws = MockWorksheet(rows)
        self.sm._get_cargos_worksheet_sync = MagicMock(return_value=ws)

        ok, msg = await self.sm.delete_cargo_report("YK1", "NON_EXISTENT")
        self.assertFalse(ok, "Mavjud bo'lmagan trek uchun delete False qaytarishi kerak!")
        self.assertEqual(len(ws.rows), 2, "Mavjud bo'lmagan trek berilganda oxirgi qator o'chirib yuborildi!")

if __name__ == "__main__":
    unittest.main()

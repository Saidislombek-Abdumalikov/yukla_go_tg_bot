import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import database
from handlers.client import (
    show_my_tracks,
    start_add_track,
    process_user_track_input
)
from handlers.admin import (
    cmd_search_track,
    state_process_track_search,
    search_and_display_track_info
)
from sheets import GoogleSheetManager, USER_TRACK_HEADERS
from states import UserTrackStates, AdminSearchTrackStates

class MockMessage:
    def __init__(self, text="", chat_id=123, message_id=456, from_user_id=123):
        self.text = text
        self.chat = MagicMock(id=chat_id)
        self.message_id = message_id
        self.from_user = MagicMock(id=from_user_id)
        self.answer = AsyncMock()

class MockState:
    def __init__(self, state=None, data=None):
        self._state = state
        self._data = data or {}

    async def get_state(self):
        return self._state

    async def set_state(self, state):
        self._state = state

    async def get_data(self):
        return self._data

    async def update_data(self, **kwargs):
        self._data.update(kwargs)

    async def clear(self):
        self._state = None
        self._data = {}

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

class TestTrackNumbersFeature(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.orig_db_path = database.DB_PATH
        database.DB_PATH = self.temp_db.name
        await database.init_db()

        self.sm = GoogleSheetManager()
        self.sm.is_configured = MagicMock(return_value=True)

        self.admin_id = 999
        self.client_id = 1001
        patcher = patch("handlers.admin.ADMIN_IDS", [self.admin_id])
        patcher.start()
        self.addCleanup(patcher.stop)

        # Approved mijoz yaratamiz
        await database.save_application(self.client_id, {
            "user_id": self.client_id,
            "username": "alibek",
            "hudud": "Toshkent shahar",
            "phone": "+998901112233",
            "extra_phone": "+998909998877",
            "first_name": "Ali",
            "last_name": "Valiyev",
            "passport_series": "AA1234567",
            "pinfl": "12345678901234",
            "address": "Chilonzor 9",
            "passport_front_id": "p_front",
            "passport_back_id": "p_back"
        })
        await database.approve_user_atomic(self.client_id)

    async def asyncTearDown(self):
        database.DB_PATH = self.orig_db_path
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    async def test_user_can_add_single_and_multiple_tracks_with_optional_description(self):
        """Mijoz trek-kodni izoh bilan yoki izohsiz, bitta yoki bir nechta qo'sha olishi kerak."""
        state = MockState(state=UserTrackStates.entering_track_code)
        msg = MockMessage(
            text="YT1001 Krossovka\nSF2002 Smartfon\nTK3003",
            from_user_id=self.client_id
        )

        with patch("handlers.client.sheet_manager.append_user_track", new=AsyncMock(return_value=(True, "ok"))) as mock_sheet:
            await process_user_track_input(msg, state)

            self.assertEqual(mock_sheet.await_count, 3)

        tracks = await database.get_user_tracks(self.client_id)
        self.assertEqual(len(tracks), 3)

        # Tekshiramiz: izohlar va trek-kodlar to'g'ri saqlanganmi
        track_map = {t["track_code"]: t["description"] for t in tracks}
        self.assertEqual(track_map.get("YT1001"), "Krossovka")
        self.assertEqual(track_map.get("SF2002"), "Smartfon")
        self.assertEqual(track_map.get("TK3003"), "")

    async def test_duplicate_track_does_not_duplicate(self):
        """Bir xil trek-kod qayta kiritilganda dublikat bo'lmasligi kerak."""
        ok1, msg1, t1 = await database.add_user_track(self.client_id, "YK1", "YT9999", "Soat")
        self.assertTrue(ok1)

        ok2, msg2, t2 = await database.add_user_track(self.client_id, "YK1", "YT9999", "Boshqa soat")
        self.assertFalse(ok2)
        self.assertIn("allaqachon", msg2.lower())

        tracks = await database.get_user_tracks(self.client_id)
        self.assertEqual(len(tracks), 1)

    async def test_admin_can_find_track_owner_by_command(self):
        """Admin /trek <kod> orqali trek egasini (Ism, ID, telefon) topa olishi kerak."""
        await database.add_user_track(self.client_id, "YK1", "TRACK777", "Futbolka")

        msg = MockMessage(text="/trek TRACK777", from_user_id=self.admin_id)
        state = MockState()

        await cmd_search_track(msg, state)

        self.assertTrue(msg.answer.called)
        answer_text = msg.answer.call_args[0][0]
        self.assertIn("TRACK777", answer_text)
        self.assertIn("Ali Valiyev", answer_text)
        self.assertIn("YK1", answer_text)
        self.assertIn("+998901112233", answer_text)
        self.assertIn("Futbolka", answer_text)

    async def test_admin_search_state_finds_owner(self):
        """Admin qidiruv holatida (FSM) trek-kod kiritganda to'g'ri topishi kerak."""
        await database.add_user_track(self.client_id, "YK1", "SF8888", "Noutbuk")

        state = MockState(state=AdminSearchTrackStates.entering_track_code)
        msg = MockMessage(text="sf8888", from_user_id=self.admin_id)

        await state_process_track_search(msg, state)

        self.assertTrue(msg.answer.called)
        answer_text = msg.answer.call_args[0][0]
        self.assertIn("SF8888", answer_text)
        self.assertIn("Ali Valiyev", answer_text)
        self.assertIn("Noutbuk", answer_text)

    async def test_admin_search_nonexistent_track_shows_not_found(self):
        """Mavjud bo'lmagan trek qidirilganda toza xato xabari chiqishi kerak."""
        msg = MockMessage(text="/trek NONEXISTENT999", from_user_id=self.admin_id)
        state = MockState()

        await cmd_search_track(msg, state)

        self.assertTrue(msg.answer.called)
        answer_text = msg.answer.call_args[0][0]
        self.assertIn("topilmadi", answer_text.lower())

    async def test_confirm_report_marks_user_track_arrived(self):
        """Yuk foto-hisoboti yuborilganda tegishli user_track statusi 'yetib_kelgan' bo'lishi kerak."""
        await database.add_user_track(self.client_id, "YK1", "ARRIVE123", "Kurtka")

        # Trek keldi deb belgilaymiz
        await database.mark_user_tracks_arrived(["ARRIVE123"])

        tracks = await database.get_user_tracks(self.client_id)
        self.assertEqual(tracks[0]["status"], "yetib_kelgan")

    async def test_sheets_import_user_tracks(self):
        """Sheets 'Mijoz treklari' jadvalidan lokal bazaga import tiklanishi kerak."""
        ws = MockWorksheet([
            list(USER_TRACK_HEADERS),
            ["2026-10-10 12:00:00", "YK1", "Ali", "Valiyev", "+998901112233", "SHEET_TRK_1", "Quloqchin", "Kutilmoqda", str(self.client_id)]
        ])
        self.sm._get_user_tracks_worksheet_sync = MagicMock(return_value=ws)

        res = await self.sm.import_all_user_tracks_to_db()
        self.assertEqual(res.count, 1)

        owner = await database.find_track_owner("SHEET_TRK_1")
        self.assertIsNotNone(owner)
        self.assertEqual(owner["first_name"], "Ali")
        self.assertEqual(owner["description"], "Quloqchin")

if __name__ == "__main__":
    unittest.main()

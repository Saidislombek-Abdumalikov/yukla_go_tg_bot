import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from handlers.admin import (
    state_user_chosen,
    state_tracks_entered,
    state_weight_entered,
    state_save_new_weight
)

class MockMessage:
    def __init__(self, text=None, chat_id=123, message_id=456, from_user_id=123, photo=None, sticker=None):
        self.text = text
        self.chat = MagicMock(id=chat_id)
        self.message_id = message_id
        self.from_user = MagicMock(id=from_user_id)
        self.photo = photo
        self.sticker = sticker
        self.answer = AsyncMock()

class TestIssue9InputValidationAndCrashPrevention(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.admin_id = 999
        patcher = patch("handlers.admin.ADMIN_IDS", [self.admin_id])
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_non_text_message_does_not_crash_handlers(self):
        # 1. state_user_chosen ga rasm/stiker yuboriladi (text=None)
        msg_photo = MockMessage(text=None, photo=[MagicMock()], from_user_id=self.admin_id)
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"msg_ids": []})

        try:
            await state_user_chosen(msg_photo, state)
        except AttributeError as e:
            self.fail(f"state_user_chosen rasm yuborilganda AttributeError bilan yiqildi: {e}")

        # 2. state_tracks_entered ga text=None
        try:
            await state_tracks_entered(msg_photo, state)
        except AttributeError as e:
            self.fail(f"state_tracks_entered rasm yuborilganda AttributeError bilan yiqildi: {e}")

        # 3. state_weight_entered ga text=None
        try:
            await state_weight_entered(msg_photo, state)
        except AttributeError as e:
            self.fail(f"state_weight_entered rasm yuborilganda AttributeError bilan yiqildi: {e}")

    async def test_nan_and_inf_weight_does_not_crash_handlers(self):
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"msg_ids": []})

        # 'nan' kiritilganda handler yiqilmasligi va xato xabari berishi kerak
        msg_nan = MockMessage(text="nan", from_user_id=self.admin_id)
        try:
            await state_weight_entered(msg_nan, state)
        except Exception as e:
            self.fail(f"state_weight_entered 'nan' kiritilganda yiqildi: {e}")

        # 'inf' kiritilganda
        msg_inf = MockMessage(text="inf", from_user_id=self.admin_id)
        try:
            await state_weight_entered(msg_inf, state)
        except Exception as e:
            self.fail(f"state_weight_entered 'inf' kiritilganda yiqildi: {e}")

    async def test_near_zero_weight_rounded_to_zero_is_rejected(self):
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"msg_ids": []})

        # 0.001 kg -> round(0.001, 2) = 0.0 kg! Nol vazn qabul qilinmasligi kerak!
        msg_zero = MockMessage(text="0.001", from_user_id=self.admin_id)
        await state_weight_entered(msg_zero, state)

        # State uploading_photo ga o'tmasligi kerak!
        state.set_state.assert_not_called()

if __name__ == "__main__":
    unittest.main()

from aiogram.fsm.state import State, StatesGroup

class RegistrationStates(StatesGroup):
    choosing_region = State()
    entering_phone = State()
    entering_first_name = State()
    entering_last_name = State()
    entering_passport = State()
    entering_pinfl = State()
    entering_address = State()
    uploading_front_photo = State()
    uploading_back_photo = State()
    confirming_data = State()

class ReportStates(StatesGroup):
    choosing_user = State()
    entering_track_codes = State()
    entering_weight = State()
    uploading_photo = State()
    confirming_report = State()

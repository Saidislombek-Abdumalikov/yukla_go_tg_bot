from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove
)

def terms_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Roziman")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def region_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌍 Viloyat"), KeyboardButton(text="🏙 Toshkent shahar")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def extra_phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Kontakt orqali yuborish", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def confirmation_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Tasdiqlash")],
            [KeyboardButton(text="🔄 Qaytadan kiritish")]
        ],
        resize_keyboard=True
    )

def reapply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆔 Id Ko'd olish")]
        ],
        resize_keyboard=True
    )

def admin_decision_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_{user_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_{user_id}")
            ]
        ]
    )

def approved_user_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆔 Mening ID kodim"), KeyboardButton(text="🇨🇳 Xitoy ombor manzili")],
            [KeyboardButton(text="📋 Shartlar va Qoidalar"), KeyboardButton(text="📞 Admin bilan bog'lanish")]
        ],
        resize_keyboard=True
    )

def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📸 Foto-otchyot yuborish", callback_data="admin_action_report"),
            ],
            [
                InlineKeyboardButton(text="👥 Mijozlar ro'yxati", callback_data="admin_action_users_1"),
                InlineKeyboardButton(text="📊 Statistika", callback_data="admin_action_stats")
            ],
            [
                InlineKeyboardButton(text="📢 Kanal sozlamasi", callback_data="admin_action_channel")
            ]
        ]
    )

def cancel_fsm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Jarayonni bekor qilish", callback_data="cancel_report")]
        ]
    )

def report_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Mijozga va kanalga yuborish", callback_data="confirm_send_report")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_report")]
        ]
    )

def user_card_actions_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📸 Foto-otchyot yaratish", callback_data=f"create_report_for_{user_id}")],
            [InlineKeyboardButton(text="🔙 Mijozlar ro'yxatiga qaytish", callback_data="admin_action_users_1")]
        ]
    )

def users_pagination_keyboard(users: list, current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    # User rows (up to 5 per page for clean mobile display)
    for u in users:
        id_code = u.get("id_code", "")
        f_name = u.get("first_name", "")
        l_name = u.get("last_name", "")
        name = f"{f_name} {l_name[:1]}.".strip()
        buttons.append([
            InlineKeyboardButton(text=f"👤 {id_code} — {name}", callback_data=f"view_user_{u.get('user_id')}")
        ])

    # Navigation buttons
    nav_row = []
    if current_page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"admin_action_users_{current_page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"📄 {current_page}/{max(1, total_pages)}", callback_data="noop"))
    if current_page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"admin_action_users_{current_page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(text="📸 Foto-otchyot yuborish", callback_data="admin_action_report"),
        InlineKeyboardButton(text="🔙 Asosiy panel", callback_data="admin_back_to_panel")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

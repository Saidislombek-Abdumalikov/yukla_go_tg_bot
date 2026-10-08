import logging
import html
import datetime
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, ChatMemberUpdated
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from config import (
    ADMIN_IDS,
    SUPPORT_ADMIN_USERNAME,
    WAREHOUSE_RECEIVER,
    WAREHOUSE_PHONE,
    format_warehouse_address,
    CARD_NUMBER,
    CARD_HOLDER,
    DEFAULT_USD_RATE,
    DEFAULT_KG_PRICE,
    REPORT_CHANNEL_ID
)
from database import (
    get_user,
    get_user_by_id_code,
    approve_user_atomic,
    reject_user_atomic,
    mark_as_synced,
    get_unsynced_users,
    get_stats,
    get_setting,
    set_setting,
    get_approved_users,
    count_approved_users,
    search_approved_users,
    save_report
)
from sheets import sheet_manager
from keyboards import (
    approved_user_menu,
    reapply_keyboard,
    admin_panel_keyboard,
    cancel_fsm_keyboard,
    report_confirm_keyboard,
    user_card_actions_keyboard,
    users_pagination_keyboard
)
from states import ReportStates

logger = logging.getLogger(__name__)
admin_router = Router()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@admin_router.callback_query(F.data.startswith("approve_"))
async def callback_approve(query: CallbackQuery, bot: Bot):
    if not is_admin(query.from_user.id):
        await query.answer("Sizda admin huquqi yo'q!", show_alert=True)
        return

    # Immediately answer query to prevent Telegram loading timeout
    await query.answer("Tekshirilmoqda...")

    user_id = int(query.data.split("_")[1])

    # Thread-safe atomic approval
    success, msg, new_id_code, updated_user = await approve_user_atomic(user_id)
    if not success:
        await query.message.answer(f"⚠️ {msg}")
        return

    # Background / immediate Google Sheets sync
    synced, sheet_msg = await sheet_manager.append_user(updated_user)
    if synced:
        await mark_as_synced(user_id)
        sheet_status = "✅ Google Sheetsga yozildi"
    else:
        sheet_status = f"⚠️ Google Sheets xatosi: {sheet_msg}"

    # Edit admin message
    try:
        current_caption = query.message.caption or ""
        await query.message.edit_caption(
            caption=(
                f"{current_caption}\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"✅ <b>ARIZA TASDIQLANDI!</b>\n"
                f"🆔 Berilgan ID: <b>{new_id_code}</b>\n"
                f"📊 {sheet_status}"
            ),
            parse_mode="HTML",
            reply_markup=None
        )
    except Exception as e:
        logger.warning(f"Admin xabarini tahrirlashda xatolik: {e}")

    # Notify User
    china_addr_text = format_warehouse_address(new_id_code)
    user_msg = (
        f"✅ <b>Tabriklaymiz! Tizimda muvaffaqiyatli ro'yxatdan o'tdingiz!</b>\n"
        f"🆔 Sizning ID kodingiz: <code>{new_id_code}</code>\n\n"
        f"{china_addr_text}\n\n"
        f"<blockquote>‼️ SKLAD KIRGIZGANINGIZDAN SO'NG SKRINSHOTINI TASHLAB BERING!\n"
        f"Sklad kirgizib va tekshirtirmay zakaz ursez u holatda biz yukizga javob bermaymiz\n\n"
        f"🔗 Endi siz ushbu id kodni adminga skrinshot qilib ko'rsatishingiz zarur</blockquote>"
    )

    try:
        await bot.send_message(
            chat_id=user_id,
            text=user_msg,
            parse_mode="HTML",
            reply_markup=approved_user_menu()
        )
    except Exception as e:
        logger.error(f"Foydalanuvchiga ({user_id}) tasdiq xabarini yuborib bo'lmadi: {e}")

@admin_router.callback_query(F.data.startswith("reject_"))
async def callback_reject(query: CallbackQuery, bot: Bot):
    if not is_admin(query.from_user.id):
        await query.answer("Sizda admin huquqi yo'q!", show_alert=True)
        return

    await query.answer("Rad etilmoqda...")

    user_id = int(query.data.split("_")[1])
    success, msg, user = await reject_user_atomic(user_id)
    if not success:
        await query.message.answer(f"⚠️ {msg}")
        return

    # Edit admin message
    try:
        current_caption = query.message.caption or ""
        await query.message.edit_caption(
            caption=(
                f"{current_caption}\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"❌ <b>ARIZA RAD ETILDI</b> (Admin tomonidan)"
            ),
            parse_mode="HTML",
            reply_markup=None
        )
    except Exception as e:
        logger.warning(f"Admin xabarini tahrirlashda xatolik: {e}")

    # Notify User
    user_msg = (
        f"❌ <b>Afsuski, arizangiz rad etildi.</b>\n\n"
        f"Qo'shimcha ma'lumot uchun: {SUPPORT_ADMIN_USERNAME}\n\n"
        f'Qaytadan urinish uchun "🆔 Id Ko\'d olish" tugmasini bosing.'
    )

    try:
        await bot.send_message(
            chat_id=user_id,
            text=user_msg,
            parse_mode="HTML",
            reply_markup=reapply_keyboard()
        )
    except Exception as e:
        logger.error(f"Foydalanuvchiga ({user_id}) rad etish xabarini yuborib bo'lmadi: {e}")

# --- Helper Functions ---
async def get_report_channel_id() -> str:
    val = await get_setting("report_channel_id")
    if val:
        return val
    return REPORT_CHANNEL_ID

async def get_current_usd_rate() -> int:
    val = await get_setting("usd_rate")
    if val and val.isdigit():
        return int(val)
    return DEFAULT_USD_RATE

def format_report_caption(user: dict, track_codes: str, weight: float, price_usd: float, price_uzs: int, is_preview: bool = False) -> str:
    first_name_esc = html.escape(user.get("first_name") or "")
    last_name_esc = html.escape(user.get("last_name") or "")
    hudud_esc = html.escape(user.get("hudud") or "")
    address_esc = html.escape(user.get("address") or "")
    phone_esc = html.escape(user.get("phone") or "")
    track_esc = html.escape(track_codes)
    id_code = user.get("id_code", "")

    header = "📸 <b>FOTO-HISOBOT PREVIEW (Tekshirish)</b>\n" if is_preview else "🚚 <b>Yukla GO — Foto-hisobot</b> 📸\n"
    footer = ""
    if not is_preview:
        footer = (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💳 <b>To'lov uchun karta:</b> <code>{CARD_NUMBER}</code>\n"
            f"👤 <b>Karta egasi:</b> {CARD_HOLDER}\n\n"
            f"<blockquote>To'lov qilgach, chekni adminga yuborishingizni so'raymiz!</blockquote>\n"
            f"📞 Admin: {SUPPORT_ADMIN_USERNAME}"
        )

    return (
        f"{header}\n"
        f"🆔 Mijoz ID: <b>{id_code}</b>\n"
        f"👤 Qabul qiluvchi: <b>{first_name_esc} {last_name_esc}</b>\n"
        f"📍 Manzil: <b>{hudud_esc}</b> {address_esc}\n"
        f"📱 Telefon: <b>{phone_esc}</b>\n\n"
        f"📦 <b>Trek-kod(lar):</b>\n"
        f"<code>{track_esc}</code>\n\n"
        f"⚖️ Og'irligi: <b>{weight} kg</b>\n"
        f"💵 Tarif: <b>{DEFAULT_KG_PRICE}$ / kg</b>\n"
        f"💰 Jami to'lov: <b>{price_usd}$</b> (<b>{price_uzs:,} so'm</b>)\n\n"
        f"{footer}"
    ).strip()

# --- Admin Management Commands & Navigation ---
@admin_router.message(Command("admin"))
@admin_router.message(Command("stat"))
async def cmd_admin_stats(message: Message):
    if not is_admin(message.from_user.id):
        return

    stats = await get_stats()
    sheets_ok = "✅ Sozlangan" if sheet_manager.is_configured() else "⚠️ Sozlanmagan (credentials.json yo'q)"
    ch_id = await get_report_channel_id()
    ch_title = await get_setting("report_channel_title", "Ulanmagan")
    channel_status = f"✅ {ch_title} (<code>{ch_id}</code>)" if ch_id else "⚠️ Ulanmagan"
    rate = await get_current_usd_rate()

    text = (
        f"📊 <b>Yukla GO — Admin Boshqaruv Paneli</b>\n\n"
        f"👥 Jami arizalar: <b>{stats['total']}</b>\n"
        f"✅ Tasdiqlangan mijozlar: <b>{stats['approved']}</b>\n"
        f"⏳ Ko'rib chiqilmoqda (Pending): <b>{stats['pending']}</b>\n"
        f"❌ Rad etilganlar: <b>{stats['rejected']}</b>\n\n"
        f"💵 Dollar kursi: <b>{rate:,} so'm</b>\n"
        f"📢 Hisobot kanali: {channel_status}\n"
        f"📑 Google Sheets: {sheets_ok}\n\n"
        f"<i>Quyidagi tugmalar orqali kerakli bo'limni tanlang:</i>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=admin_panel_keyboard())

@admin_router.callback_query(F.data == "admin_back_to_panel")
@admin_router.callback_query(F.data == "admin_action_stats")
async def callback_admin_panel(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("Sizda huquq yo'q!", show_alert=True)
        return
    await query.answer()

    stats = await get_stats()
    sheets_ok = "✅ Sozlangan" if sheet_manager.is_configured() else "⚠️ Sozlanmagan (credentials.json yo'q)"
    ch_id = await get_report_channel_id()
    ch_title = await get_setting("report_channel_title", "Ulanmagan")
    channel_status = f"✅ {ch_title} (<code>{ch_id}</code>)" if ch_id else "⚠️ Ulanmagan"
    rate = await get_current_usd_rate()

    text = (
        f"📊 <b>Yukla GO — Admin Boshqaruv Paneli</b>\n\n"
        f"👥 Jami arizalar: <b>{stats['total']}</b>\n"
        f"✅ Tasdiqlangan mijozlar: <b>{stats['approved']}</b>\n"
        f"⏳ Ko'rib chiqilmoqda (Pending): <b>{stats['pending']}</b>\n"
        f"❌ Rad etilganlar: <b>{stats['rejected']}</b>\n\n"
        f"💵 Dollar kursi: <b>{rate:,} so'm</b>\n"
        f"📢 Hisobot kanali: {channel_status}\n"
        f"📑 Google Sheets: {sheets_ok}\n\n"
        f"<i>Quyidagi tugmalar orqali kerakli bo'limni tanlang:</i>"
    )
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=admin_panel_keyboard())
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=admin_panel_keyboard())

# --- Currency Rate Command ---
@admin_router.message(Command("kurs"))
async def cmd_set_kurs(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        rate = await get_current_usd_rate()
        await message.answer(
            f"💵 Hozirgi dollar kursi: <b>{rate:,} so'm</b>\n\n"
            f"Kursni o'zgartirish uchun: <code>/kurs 11800</code> yoki <code>/kurs 12800</code> deb yozing.",
            parse_mode="HTML"
        )
        return

    new_val = parts[1].strip().replace(" ", "").replace(",", "")
    if new_val.isdigit() and int(new_val) > 0:
        await set_setting("usd_rate", new_val)
        await message.answer(f"✅ Dollar kursi muvaffaqiyatli saqlandi: <b>{int(new_val):,} so'm</b>", parse_mode="HTML")
    else:
        await message.answer("⚠️ Noto'g'ri kurs qiymati kiritildi. Masalan: <code>/kurs 11800</code>", parse_mode="HTML")

# --- Telegram Channel Connection & Auto-detection ---
@admin_router.channel_post()
async def on_channel_post(message: Message):
    chat = message.chat
    await set_setting("report_channel_id", str(chat.id))
    if chat.title:
        await set_setting("report_channel_title", chat.title)
    logger.info(f"Yangi xabardan hisobot kanali aniqlandi: {chat.title} ({chat.id})")

@admin_router.my_chat_member()
async def on_my_chat_member(event: ChatMemberUpdated):
    if event.chat.type in ["channel", "supergroup"]:
        chat = event.chat
        await set_setting("report_channel_id", str(chat.id))
        if chat.title:
            await set_setting("report_channel_title", chat.title)
        logger.info(f"Bot kanalda admin qilindi: {chat.title} ({chat.id})")

@admin_router.message(F.forward_from_chat, F.chat.type == "private")
async def on_forward_channel_message(message: Message):
    if not is_admin(message.from_user.id):
        return
    chat = message.forward_from_chat
    if chat.type in ["channel", "supergroup"]:
        await set_setting("report_channel_id", str(chat.id))
        if chat.title:
            await set_setting("report_channel_title", chat.title)
        await message.answer(
            f"✅ <b>Telegram kanal muvaffaqiyatli ulandi!</b>\n\n"
            f"📢 Kanal: <b>{chat.title}</b>\n"
            f"🆔 ID: <code>{chat.id}</code>\n\n"
            f"Barcha tasdiqlangan foto-otchyotlar ushbu kanalga ham avtomatik joylanadi.",
            parse_mode="HTML"
        )

@admin_router.message(Command("set_channel"))
async def cmd_set_channel(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        curr = await get_report_channel_id()
        await message.answer(
            f"📢 <b>Hisobot kanali</b>\n\nHozirgi ulangan kanal ID: <code>{curr or 'Ulanmagan'}</code>\n\n"
            f"<b>Kanalni ulash usullari:</b>\n"
            f"1. Kanaldan istalgan xabarni botga forward qiling\n"
            f"2. Yoki kanalda bitta ixtiyoriy xabar (masalan 'salom') yozing\n"
            f"3. Yoki kanal ID sini kiriting: <code>/set_channel -100xxxxxxxxxx</code>",
            parse_mode="HTML"
        )
        return

    target = parts[1].strip()
    try:
        chat = await bot.get_chat(target)
        await set_setting("report_channel_id", str(chat.id))
        if chat.title:
            await set_setting("report_channel_title", chat.title)
        await message.answer(f"✅ Kanal muvaffaqiyatli ulandi: <b>{chat.title}</b> (<code>{chat.id}</code>)", parse_mode="HTML")
    except Exception as e:
        if target.startswith("-100") or (target.startswith("-") and target[1:].isdigit()):
            await set_setting("report_channel_id", target)
            await message.answer(f"✅ Kanal ID saqlandi: <code>{target}</code>", parse_mode="HTML")
        else:
            await message.answer(f"⚠️ Xatolik: {e}\nIltimos, kanaldan bitta xabarni botga forward qiling.")

@admin_router.callback_query(F.data == "admin_action_channel")
async def callback_admin_channel(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("Sizda huquq yo'q!", show_alert=True)
        return
    await query.answer()

    curr_id = await get_report_channel_id()
    curr_title = await get_setting("report_channel_title", "Noma'lum")
    text = (
        f"📢 <b>Telegram Kanal Sozlamalari</b>\n\n"
        f"Ulangan kanal: <b>{curr_title if curr_id else 'Ulanmagan'}</b>\n"
        f"Kanal ID: <code>{curr_id or 'Mavjud emas'}</code>\n\n"
        f"<b>Qanday ulash mumkin?</b>\n"
        f"1. Botni kanalingizga qo'shib, <b>Admin</b> huquqini bering.\n"
        f"2. Kanaldan istalgan xabarni botga <b>forward</b> qiling (yoki kanalda bitta post yozing).\n"
        f"Bot kanalni avtomatik aniqlaydi va eslab qoladi!"
    )
    await query.message.answer(text, parse_mode="HTML")

# --- Users List & Pagination ---
@admin_router.message(Command("users"))
async def cmd_users_list(message: Message):
    if not is_admin(message.from_user.id):
        return
    await show_users_page(message.chat.id, message.bot, page=1)

@admin_router.callback_query(F.data.startswith("admin_action_users_"))
async def callback_users_page(query: CallbackQuery, bot: Bot):
    if not is_admin(query.from_user.id):
        await query.answer("Sizda huquq yo'q!", show_alert=True)
        return
    await query.answer()
    page = int(query.data.split("_")[3])
    await show_users_page(query.message.chat.id, bot, page=page, edit_message_id=query.message.message_id)

async def show_users_page(chat_id: int, bot: Bot, page: int = 1, edit_message_id: int = None):
    limit = 5
    total = await count_approved_users()
    total_pages = max(1, (total + limit - 1) // limit)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * limit

    users = await get_approved_users(limit=limit, offset=offset)
    if not users:
        text = "👥 Hozircha tasdiqlangan mijozlar mavjud emas."
        kb = admin_panel_keyboard()
    else:
        text = (
            f"👥 <b>Tasdiqlangan Mijozlar Ro'yxati</b>\n"
            f"Jami mijozlar: <b>{total} ta</b> (Sahifa: {page}/{total_pages})\n\n"
            f"<i>Mijoz haqida ma'lumot olish yoki unga foto-otchyot yuborish uchun ustiga bosing:</i>"
        )
        kb = users_pagination_keyboard(users, current_page=page, total_pages=total_pages)

    if edit_message_id:
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=edit_message_id, text=text, parse_mode="HTML", reply_markup=kb)
            return
        except Exception:
            pass
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=kb)

# --- View User Profile ---
@admin_router.callback_query(F.data.startswith("view_user_"))
async def callback_view_user(query: CallbackQuery, bot: Bot):
    if not is_admin(query.from_user.id):
        await query.answer("Sizda huquq yo'q!", show_alert=True)
        return
    await query.answer()

    user_id = int(query.data.split("_")[2])
    user = await get_user(user_id)
    if not user:
        await query.message.answer("❌ Foydalanuvchi topilmadi.")
        return

    first_name_esc = html.escape(user.get("first_name") or "")
    last_name_esc = html.escape(user.get("last_name") or "")
    address_esc = html.escape(user.get("address") or "")
    hudud_esc = html.escape(user.get("hudud") or "")
    username_esc = html.escape(user.get("username") or "")

    info_text = (
        f"👤 <b>Mijoz Profili:</b>\n\n"
        f"🆔 ID Kod: <b>{user.get('id_code') or 'Berilmagan'}</b>\n"
        f"📌 Holati: <b>{user.get('status')}</b>\n"
        f"👤 Ism-familiya: {first_name_esc} {last_name_esc}\n"
        f"📍 Hudud: {hudud_esc}\n"
        f"📱 Telefon: {user.get('phone')}\n"
        f"🪪 Pasport: {user.get('passport_series')}\n"
        f"🔢 JShShIR: {user.get('pinfl')}\n"
        f"📍 Yashash manzili: {address_esc}\n"
        f"🆔 Telegram ID: <code>{user.get('user_id')}</code>\n"
        f"👤 Username: @{username_esc if username_esc else 'yoq'}\n"
        f"📅 Ro'yxatdan o'tgan: {user.get('created_at')}"
    )

    await query.message.answer(
        info_text,
        parse_mode="HTML",
        reply_markup=user_card_actions_keyboard(user_id)
    )

@admin_router.message(Command("user"))
async def cmd_view_user(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("Foydalanuvchi ID kodini yoki Telegram ID sini kiriting.\nMasalan: <code>/user YK1</code>", parse_mode="HTML")
        return

    query_val = parts[1].strip()
    user = None
    if query_val.isdigit():
        user = await get_user_by_id_code(f"YK{query_val}")
        if not user:
            user = await get_user(int(query_val))
    if not user:
        user = await get_user_by_id_code(query_val.upper())

    if not user:
        await message.answer(f"❌ '{html.escape(query_val)}' bo'yicha foydalanuvchi topilmadi.")
        return

    first_name_esc = html.escape(user.get("first_name") or "")
    last_name_esc = html.escape(user.get("last_name") or "")
    address_esc = html.escape(user.get("address") or "")
    hudud_esc = html.escape(user.get("hudud") or "")
    username_esc = html.escape(user.get("username") or "")

    info_text = (
        f"👤 <b>Foydalanuvchi ma'lumotlari:</b>\n\n"
        f"🆔 ID Kod: <b>{user.get('id_code') or 'Berilmagan'}</b>\n"
        f"📌 Holati: <b>{user.get('status')}</b>\n"
        f"👤 Ism: {first_name_esc} {last_name_esc}\n"
        f"📍 Hudud: {hudud_esc}\n"
        f"📱 Telefon: {user.get('phone')}\n"
        f"🪪 Pasport: {user.get('passport_series')}\n"
        f"🔢 JShShIR: {user.get('pinfl')}\n"
        f"📍 Yashash manzili: {address_esc}\n"
        f"🆔 Telegram ID: <code>{user.get('user_id')}</code>\n"
        f"👤 Username: @{username_esc if username_esc else 'yoq'}\n"
        f"📅 Sana: {user.get('created_at')}"
    )

    await message.answer(
        info_text,
        parse_mode="HTML",
        reply_markup=user_card_actions_keyboard(user["user_id"])
    )

@admin_router.message(Command("sync_sheets"))
async def cmd_sync_sheets(message: Message):
    if not is_admin(message.from_user.id):
        return

    if not sheet_manager.is_configured():
        await message.answer("⚠️ Google Sheets sozlanmagan! <code>credentials.json</code> faylini bot papkasiga joylashtiring.", parse_mode="HTML")
        return

    unsynced = await get_unsynced_users()
    if not unsynced:
        await message.answer("✅ Barcha tasdiqlangan foydalanuvchilar allaqachon Google Sheetsga yozilgan!")
        return

    success_count = 0
    fail_count = 0
    await message.answer(f"🔄 {len(unsynced)} ta foydalanuvchi sinxronlanmoqda...")

    for user in unsynced:
        ok, msg = await sheet_manager.append_user(user)
        if ok:
            await mark_as_synced(user["user_id"])
            success_count += 1
        else:
            fail_count += 1

    await message.answer(
        f"✅ Sinxronizatsiya yakunlandi!\n"
        f"Muvaffaqiyatli: {success_count} ta\n"
        f"Xatolar: {fail_count} ta"
    )

# --- FOTO-OTCHYOT FSM FLOW ---
@admin_router.message(Command("otchyot"))
@admin_router.message(Command("report"))
@admin_router.callback_query(F.data == "admin_action_report")
async def start_report_entry(event: Message | CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    if not is_admin(user_id):
        if isinstance(event, CallbackQuery):
            await event.answer("Sizda huquq yo'q!", show_alert=True)
        return

    await state.clear()
    text = (
        f"📸 <b>Foto-otchyot yaratish</b>\n\n"
        f"Qaysi mijozga foto-otchyot yubormoqchisiz?\n"
        f"Mijozning <b>ID kodini</b> yoki <b>raqamini</b> kiriting:\n"
        f"Masalan: <code>YK1</code> yoki shunchaki <code>1</code>"
    )

    if isinstance(event, CallbackQuery):
        await event.answer()
        prompt = await event.message.answer(text, parse_mode="HTML", reply_markup=cancel_fsm_keyboard())
    else:
        prompt = await event.answer(text, parse_mode="HTML", reply_markup=cancel_fsm_keyboard())

    await state.set_state(ReportStates.choosing_user)
    await state.update_data(msg_ids=[prompt.message_id])

@admin_router.callback_query(F.data.startswith("create_report_for_"))
async def start_report_for_user(query: CallbackQuery, state: FSMContext):
    if not is_admin(query.from_user.id):
        await query.answer("Sizda huquq yo'q!", show_alert=True)
        return
    await query.answer()

    target_user_id = int(query.data.split("_")[3])
    user = await get_user(target_user_id)
    if not user or user.get("status") != "approved":
        await query.message.answer("⚠️ Bu mijoz bazada topilmadi yoki hali tasdiqlanmagan!")
        return

    await state.clear()
    first_name_esc = html.escape(user.get("first_name") or "")
    last_name_esc = html.escape(user.get("last_name") or "")

    prompt = await query.message.answer(
        f"👤 Mijoz: <b>{first_name_esc} {last_name_esc}</b> (<code>{user.get('id_code')}</code>)\n"
        f"📱 Telefon: <b>{user.get('phone')}</b>\n\n"
        f"📦 <b>1-qadam:</b> Trek-kod(lar)ni kiriting:\n"
        f"<i>(Bir nechta bo'lsa yangi qatordan yoki vergul bilan ajrating)</i>",
        parse_mode="HTML",
        reply_markup=cancel_fsm_keyboard()
    )

    await state.set_state(ReportStates.entering_track_codes)
    await state.update_data(target_user=user, msg_ids=[prompt.message_id])

@admin_router.message(ReportStates.choosing_user)
async def state_user_chosen(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    msg_ids = data.get("msg_ids", [])
    msg_ids.append(message.message_id)

    query_val = message.text.strip()
    user = None
    if query_val.isdigit():
        user = await get_user_by_id_code(f"YK{query_val}")
        if not user:
            user = await get_user(int(query_val))
    else:
        user = await get_user_by_id_code(query_val.upper())

    if not user or user.get("status") != "approved":
        err_msg = await message.answer(
            f"❌ <b>'{html.escape(query_val)}'</b> bo'yicha tasdiqlangan mijoz topilmadi!\n"
            f"Iltimos, qaytadan kiriting (masalan: <code>YK1</code> yoki <code>1</code>):",
            parse_mode="HTML",
            reply_markup=cancel_fsm_keyboard()
        )
        msg_ids.append(err_msg.message_id)
        await state.update_data(msg_ids=msg_ids)
        return

    first_name_esc = html.escape(user.get("first_name") or "")
    last_name_esc = html.escape(user.get("last_name") or "")

    prompt = await message.answer(
        f"👤 Tanlangan mijoz: <b>{first_name_esc} {last_name_esc}</b> (<code>{user.get('id_code')}</code>)\n"
        f"📱 Telefon: <b>{user.get('phone')}</b>\n\n"
        f"📦 <b>1-qadam:</b> Trek-kod(lar)ni kiriting:\n"
        f"<i>(Bir nechta bo'lsa yangi qatordan yoki vergul bilan ajrating)</i>",
        parse_mode="HTML",
        reply_markup=cancel_fsm_keyboard()
    )
    msg_ids.append(prompt.message_id)

    await state.set_state(ReportStates.entering_track_codes)
    await state.update_data(target_user=user, msg_ids=msg_ids)

@admin_router.message(ReportStates.entering_track_codes)
async def state_tracks_entered(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    msg_ids = data.get("msg_ids", [])
    msg_ids.append(message.message_id)

    tracks = message.text.strip()
    if not tracks:
        prompt = await message.answer("⚠️ Iltimos, kamida bitta trek-kod kiriting:", reply_markup=cancel_fsm_keyboard())
        msg_ids.append(prompt.message_id)
        await state.update_data(msg_ids=msg_ids)
        return

    prompt = await message.answer(
        f"✅ Trek-kod(lar) qabul qilindi.\n\n"
        f"⚖️ <b>2-qadam:</b> Yukning og'irligini kiriting (kg):\n"
        f"<i>(Masalan: <code>2.5</code> yoki <code>0.8</code>)</i>",
        parse_mode="HTML",
        reply_markup=cancel_fsm_keyboard()
    )
    msg_ids.append(prompt.message_id)

    await state.set_state(ReportStates.entering_weight)
    await state.update_data(track_codes=tracks, msg_ids=msg_ids)

@admin_router.message(ReportStates.entering_weight)
async def state_weight_entered(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    msg_ids = data.get("msg_ids", [])
    msg_ids.append(message.message_id)

    weight_str = message.text.strip().replace(",", ".")
    try:
        weight = float(weight_str)
        if weight <= 0:
            raise ValueError()
    except ValueError:
        prompt = await message.answer("⚠️ Iltimos, og'irlikni to'g'ri musbat sonda kiriting (masalan: <code>2.5</code>):", parse_mode="HTML", reply_markup=cancel_fsm_keyboard())
        msg_ids.append(prompt.message_id)
        await state.update_data(msg_ids=msg_ids)
        return

    weight = round(weight, 2)
    price_usd = round(weight * DEFAULT_KG_PRICE, 2)
    rate = await get_current_usd_rate()
    price_uzs = int(round(price_usd * rate))

    prompt = await message.answer(
        f"⚖️ Og'irlik: <b>{weight} kg</b>\n"
        f"💰 Hisoblangan narx: <b>{price_usd}$</b> (<b>{price_uzs:,} so'm</b>)\n\n"
        f"📸 <b>3-qadam:</b> Yukning tarozidagi yoki ombordagi rasmini yuboring:",
        parse_mode="HTML",
        reply_markup=cancel_fsm_keyboard()
    )
    msg_ids.append(prompt.message_id)

    await state.set_state(ReportStates.uploading_photo)
    await state.update_data(
        weight=weight,
        price_usd=price_usd,
        price_uzs=price_uzs,
        msg_ids=msg_ids
    )

@admin_router.message(ReportStates.uploading_photo, F.photo)
async def state_photo_uploaded(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    msg_ids = data.get("msg_ids", [])
    msg_ids.append(message.message_id)

    photo_file_id = message.photo[-1].file_id
    user = data.get("target_user", {})
    track_codes = data.get("track_codes", "")
    weight = data.get("weight", 0.0)
    price_usd = data.get("price_usd", 0.0)
    price_uzs = data.get("price_uzs", 0)

    preview_caption = format_report_caption(
        user=user,
        track_codes=track_codes,
        weight=weight,
        price_usd=price_usd,
        price_uzs=price_uzs,
        is_preview=True
    )

    preview_msg = await bot.send_photo(
        chat_id=message.chat.id,
        photo=photo_file_id,
        caption=preview_caption,
        parse_mode="HTML",
        reply_markup=report_confirm_keyboard()
    )
    msg_ids.append(preview_msg.message_id)

    await state.set_state(ReportStates.confirming_report)
    await state.update_data(photo_file_id=photo_file_id, msg_ids=msg_ids)

@admin_router.callback_query(F.data == "confirm_send_report", ReportStates.confirming_report)
async def callback_confirm_report(query: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(query.from_user.id):
        await query.answer("Sizda huquq yo'q!", show_alert=True)
        return
    await query.answer("Yuborilmoqda...")

    data = await state.get_data()
    user = data.get("target_user", {})
    track_codes = data.get("track_codes", "")
    weight = data.get("weight", 0.0)
    price_usd = data.get("price_usd", 0.0)
    price_uzs = data.get("price_uzs", 0)
    photo_file_id = data.get("photo_file_id", "")
    msg_ids = data.get("msg_ids", [])

    final_caption = format_report_caption(
        user=user,
        track_codes=track_codes,
        weight=weight,
        price_usd=price_usd,
        price_uzs=price_uzs,
        is_preview=False
    )

    # 1. Send to client in Telegram
    user_sent = False
    user_err = ""
    try:
        await bot.send_photo(
            chat_id=user["user_id"],
            photo=photo_file_id,
            caption=final_caption,
            parse_mode="HTML"
        )
        user_sent = True
    except Exception as e:
        logger.error(f"Foydalanuvchiga ({user.get('user_id')}) foto-otchyot yuborishda xatolik: {e}")
        user_err = str(e)

    # 2. Send to Telegram Channel (if connected)
    channel_id = await get_report_channel_id()
    channel_sent = False
    channel_err = ""
    if channel_id:
        try:
            target_ch = int(channel_id) if channel_id.startswith("-") and channel_id[1:].isdigit() else channel_id
            await bot.send_photo(
                chat_id=target_ch,
                photo=photo_file_id,
                caption=final_caption,
                parse_mode="HTML"
            )
            channel_sent = True
        except Exception as e:
            logger.error(f"Kanalga ({channel_id}) foto-otchyot yuborishda xatolik: {e}")
            channel_err = str(e)

    # 3. Save to SQLite database
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
    await save_report({
        "user_id": user.get("user_id"),
        "id_code": user.get("id_code"),
        "full_name": full_name,
        "phone": user.get("phone"),
        "track_codes": track_codes,
        "weight": weight,
        "price_usd": price_usd,
        "price_uzs": price_uzs,
        "photo_file_id": photo_file_id,
        "created_at": now_str
    })

    # 4. Save to Google Sheets "Yuklar" tab
    sheet_ok, sheet_msg = await sheet_manager.append_cargo({
        "created_at": now_str,
        "id_code": user.get("id_code"),
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "phone": user.get("phone", ""),
        "hudud": user.get("hudud", ""),
        "track_codes": track_codes,
        "weight": weight,
        "price_usd": price_usd,
        "price_uzs": price_uzs
    })

    # 5. Clean Admin Chat (Delete temporary questions, user inputs, preview photo)
    for mid in msg_ids:
        try:
            await bot.delete_message(chat_id=query.message.chat.id, message_id=mid)
        except Exception:
            pass

    # 6. Send clean single confirmation message to Admin
    user_status_icon = "✅ Yetkazildi" if user_sent else f"⚠️ Xato: {user_err}"
    ch_status_icon = "✅ Joylandi" if channel_sent else (f"⚠️ Xato: {channel_err}" if channel_id else "⚠️ Kanal ulanmagan")
    sheet_status_icon = "✅ Yozildi" if sheet_ok else f"⚠️ {sheet_msg}"

    summary_text = (
        f"✅ <b>FOTO-HISOBOT MUVAFFAQIYATLI YUBORILDI!</b>\n\n"
        f"🆔 Mijoz ID: <b>{user.get('id_code')}</b> ({full_name})\n"
        f"📦 Trek-kod(lar): <code>{html.escape(track_codes)}</code>\n"
        f"⚖️ Og'irlik: <b>{weight} kg</b>\n"
        f"💰 Summa: <b>{price_usd}$</b> (<b>{price_uzs:,} so'm</b>)\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Mijozga:</b> {user_status_icon}\n"
        f"📢 <b>Kanalga:</b> {ch_status_icon}\n"
        f"📊 <b>Google Sheets (Yuklar):</b> {sheet_status_icon}"
    )

    await bot.send_message(
        chat_id=query.message.chat.id,
        text=summary_text,
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard()
    )

    await state.clear()

@admin_router.message(Command("cancel"))
@admin_router.callback_query(F.data == "cancel_report")
async def cancel_report_flow(event: Message | CallbackQuery, state: FSMContext, bot: Bot):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    data = await state.get_data()
    msg_ids = data.get("msg_ids", [])
    chat_id = event.chat.id if isinstance(event, Message) else event.message.chat.id

    for mid in msg_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass

    if isinstance(event, CallbackQuery):
        await event.answer("Bekor qilindi")

    await bot.send_message(
        chat_id=chat_id,
        text="❌ Foto-otchyot jarayoni bekor qilindi.",
        reply_markup=admin_panel_keyboard()
    )
    await state.clear()

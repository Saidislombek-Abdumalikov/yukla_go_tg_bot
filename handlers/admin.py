import os
import logging
import html
import datetime
import re
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, ChatMemberUpdated, FSInputFile
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
    REPORT_CHANNEL_ID,
    ID_PREFIX,
    DB_PATH
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
    save_report,
    mark_reports_paid,
    get_user_reports,
    get_report_by_id,
    update_report_weight,
    update_report_track_codes,
    delete_report
)
from sheets import sheet_manager
from keyboards import (
    approved_user_menu,
    reapply_keyboard,
    admin_panel_keyboard,
    cancel_fsm_keyboard,
    report_confirm_keyboard,
    user_card_actions_keyboard,
    users_pagination_keyboard,
    user_reports_list_keyboard,
    report_manage_keyboard,
    report_delete_confirm_keyboard,
    cancel_edit_report_keyboard
)
from states import ReportStates, EditReportStates

logger = logging.getLogger(__name__)
admin_router = Router()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def check_admin_or_reject(event: Message | CallbackQuery) -> bool:
    user_id = event.from_user.id if event.from_user else 0
    if not is_admin(user_id):
        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except Exception:
                pass
        # Boshqalar uchun mutlaqo hech qanday javob qaytarmaydi (sukut saqlaydi)
        return False
    return True

@admin_router.callback_query(F.data.startswith("approve_"))
async def callback_approve(query: CallbackQuery, bot: Bot):
    if not await check_admin_or_reject(query):
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
    if not await check_admin_or_reject(query):
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
    if not await check_admin_or_reject(message):
        return

    stats = await get_stats()
    rate = await get_current_usd_rate()

    text = (
        f"📊 <b>Yukla GO — Admin Boshqaruv Paneli</b>\n\n"
        f"👥 Jami arizalar: <b>{stats['total']}</b>\n"
        f"✅ Tasdiqlangan mijozlar: <b>{stats['approved']}</b>\n"
        f"⏳ Ko'rib chiqilmoqda (Pending): <b>{stats['pending']}</b>\n"
        f"❌ Rad etilganlar: <b>{stats['rejected']}</b>\n\n"
        f"💵 Hozirgi dollar kursi: <b>{rate:,} so'm</b>\n\n"
        f"Tezkor buyruqlar:\n"
        f"• <code>/tolandi YK1 YK2</code> — To'lovni tasdiqlash\n"
        f"• <code>/report</code> — Foto-otchyot yaratish\n"
        f"• <code>/kurs 12800</code> — Kursni o'zgartirish\n\n"
        f"<i>Quyidagi tugmalar orqali kerakli bo'limni tanlang:</i>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=admin_panel_keyboard())

@admin_router.callback_query(F.data == "admin_back_to_panel")
@admin_router.callback_query(F.data == "admin_action_stats")
async def callback_admin_panel(query: CallbackQuery):
    if not await check_admin_or_reject(query):
        return
    await query.answer()

    stats = await get_stats()
    rate = await get_current_usd_rate()

    text = (
        f"📊 <b>Yukla GO — Admin Boshqaruv Paneli</b>\n\n"
        f"👥 Jami arizalar: <b>{stats['total']}</b>\n"
        f"✅ Tasdiqlangan mijozlar: <b>{stats['approved']}</b>\n"
        f"⏳ Ko'rib chiqilmoqda (Pending): <b>{stats['pending']}</b>\n"
        f"❌ Rad etilganlar: <b>{stats['rejected']}</b>\n\n"
        f"💵 Hozirgi dollar kursi: <b>{rate:,} so'm</b>\n\n"
        f"Tezkor buyruqlar:\n"
        f"• <code>/tolandi YK1 YK2</code> — To'lovni tasdiqlash\n"
        f"• <code>/report</code> — Foto-otchyot yaratish\n"
        f"• <code>/kurs 12800</code> — Kursni o'zgartirish\n\n"
        f"<i>Quyidagi tugmalar orqali kerakli bo'limni tanlang:</i>"
    )
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=admin_panel_keyboard())
    except Exception:
        await query.message.answer(text, parse_mode="HTML", reply_markup=admin_panel_keyboard())

# --- Currency Rate Command ---
@admin_router.message(Command("kurs"))
async def cmd_set_kurs(message: Message):
    if not await check_admin_or_reject(message):
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

# --- Parse ID Codes Helper ---
def parse_id_codes(text: str) -> list:
    tokens = re.findall(r'[a-zA-Z]*\d+', text)
    result = []
    for t in tokens:
        t = t.strip().upper()
        if t.isdigit():
            code = f"{ID_PREFIX}{t}"
        elif not t.startswith(ID_PREFIX):
            num = re.sub(r'^\D+', '', t)
            code = f"{ID_PREFIX}{num}"
        else:
            code = t
        if code not in result:
            result.append(code)
    return result

# --- Mark Cargos Paid Command (/tolandi) ---
@admin_router.message(Command("tolandi"))
async def cmd_mark_paid(message: Message, bot: Bot):
    if not await check_admin_or_reject(message):
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "ℹ️ <b>To'langan mijoz ID kodlarini kiriting:</b>\n\n"
            "Bir yoki bir nechta ID yozishingiz mumkin:\n"
            "• Bitta mijoz: <code>/tolandi YK1</code>\n"
            "• Bir nechta mijoz: <code>/tolandi YK1 YK2 YK5</code> (yoki <code>/tolandi 1, 2, 5</code>)",
            parse_mode="HTML"
        )
        return

    raw_input = parts[1]
    id_codes = parse_id_codes(raw_input)
    if not id_codes:
        await message.answer("⚠️ Hech qanday ID kod topilmadi. Masalan: <code>/tolandi YK1 YK2</code>", parse_mode="HTML")
        return

    # 1. Google Sheetsda 'To'landi' deb yangilash
    sheet_updated_count, sheet_updated_codes = await sheet_manager.mark_cargos_paid(id_codes)

    # 2. SQLite bazada tolandi deb belgilash
    db_updated_count, db_updated_codes = await mark_reports_paid(id_codes)

    # Haqiqatan ham qarzdor yuk bo'lgan va to'langan ID lar to'plami
    actually_paid_set = {str(c).upper().strip() for c in (sheet_updated_codes + db_updated_codes)}

    notified_list = []
    success_count = 0

    for code in id_codes:
        clean_code = str(code).upper().strip()
        user = await get_user_by_id_code(clean_code)
        first_name_esc = html.escape(user.get("first_name", "")) if user else ""

        if clean_code in actually_paid_set:
            # Haqiqatan ham qarzdor yuk bo'lgan va to'landi deb belgilandi!
            if user:
                try:
                    await bot.send_message(
                        chat_id=user["user_id"],
                        text=(
                            f"✅ <b>Hurmatli {first_name_esc}, to'lovingiz qabul qilindi!</b>\n\n"
                            f"Yukingiz uchun to'lov to'liq tasdiqlandi. "
                            f"Hamkorligingiz uchun rahmat! 😊"
                        ),
                        parse_mode="HTML"
                    )
                    notified_list.append(f"• <b>{code}</b> ({first_name_esc}) — ✅ To'landi (Mijozga xabar bordi)")
                except Exception:
                    notified_list.append(f"• <b>{code}</b> ({first_name_esc}) — ✅ To'landi (Mijoz botni bloklagan)")
            else:
                notified_list.append(f"• <b>{code}</b> — ✅ To'landi (Lekin mijoz bazada topilmadi)")
            success_count += 1
        else:
            # Bu mijoz bo'yicha qarzdor yuk bo'lmagan (allaqachon to'langan yoki yuk kiritilmagan)
            if user:
                notified_list.append(f"• <b>{code}</b> ({first_name_esc}) — ℹ️ Qarzdor yuk yo'q (allaqachon to'langan)")
            else:
                notified_list.append(f"• <b>{code}</b> — ⚠️ Bazada bunday mijoz topilmadi")

    if success_count > 0:
        summary = (
            f"🟢 <b>TO'LOV TASDIQLANDI!</b>\n\n"
            f"📊 Google Sheets va bazada <b>{max(sheet_updated_count, db_updated_count)} ta</b> yuk holati <b>'To'landi'</b> deb yangilandi.\n\n"
            f"<b>Mijozlar natijasi:</b>\n" + "\n".join(notified_list)
        )
    else:
        summary = (
            f"ℹ️ <b>QARZDOR YUK TOPILMADI</b>\n\n"
            f"Kiritilgan mijoz(lar)da to'lanmagan qarzdor yuk topilmadi.\n"
            f"<i>Mijozlarga hech qanday xabar yuborilmadi.</i>\n\n"
            f"<b>Holat:</b>\n" + "\n".join(notified_list)
        )
    await message.answer(summary, parse_mode="HTML")

# --- Telegram Channel Connection & Auto-detection ---
@admin_router.channel_post()
async def on_channel_post(message: Message):
    curr = await get_setting("report_channel_id")
    if not curr:
        chat = message.chat
        await set_setting("report_channel_id", str(chat.id))
        if chat.title:
            await set_setting("report_channel_title", chat.title)
        logger.info(f"Yangi xabardan hisobot kanali aniqlandi: {chat.title} ({chat.id})")

@admin_router.my_chat_member()
async def on_my_chat_member(event: ChatMemberUpdated):
    if not event.from_user or not is_admin(event.from_user.id):
        return
    if event.chat.type in ["channel", "supergroup"]:
        chat = event.chat
        await set_setting("report_channel_id", str(chat.id))
        if chat.title:
            await set_setting("report_channel_title", chat.title)
        logger.info(f"Bot kanalda admin qilindi: {chat.title} ({chat.id})")

@admin_router.message(F.forward_from_chat, F.chat.type == "private")
async def on_forward_channel_message(message: Message):
    if not await check_admin_or_reject(message):
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
    if not await check_admin_or_reject(message):
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


# --- Users List & Pagination ---
@admin_router.message(Command("users"))
async def cmd_users_list(message: Message):
    if not await check_admin_or_reject(message):
        return
    await show_users_page(message.chat.id, message.bot, page=1)

@admin_router.callback_query(F.data.startswith("admin_action_users_"))
async def callback_users_page(query: CallbackQuery, bot: Bot):
    if not await check_admin_or_reject(query):
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
    if not await check_admin_or_reject(query):
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

    cargo_count = user.get("cargo_count", 0)
    unpaid_count = user.get("unpaid_cargo_count", 0)
    paid_count = max(0, cargo_count - unpaid_count)

    cargos_stat = f"📦 Jami yuklar: <b>{cargo_count} ta</b>"
    if cargo_count > 0:
        cargos_stat += f" (🟢 {paid_count} to'langan, 🔴 {unpaid_count} qarzdor)"

    info_text = (
        f"👤 <b>Mijoz Profili:</b>\n\n"
        f"🆔 ID Kod: <b>{user.get('id_code') or 'Berilmagan'}</b>\n"
        f"📌 Holati: <b>{user.get('status')}</b>\n"
        f"👤 Ism-familiya: {first_name_esc} {last_name_esc}\n"
        f"{cargos_stat}\n"
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
        reply_markup=user_card_actions_keyboard(user_id, cargo_count)
    )

@admin_router.message(Command("user"))
async def cmd_view_user(message: Message, bot: Bot):
    if not await check_admin_or_reject(message):
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

    cargo_count = user.get("cargo_count", 0)
    unpaid_count = user.get("unpaid_cargo_count", 0)
    paid_count = max(0, cargo_count - unpaid_count)

    cargos_stat = f"📦 Jami yuklar: <b>{cargo_count} ta</b>"
    if cargo_count > 0:
        cargos_stat += f" (🟢 {paid_count} to'langan, 🔴 {unpaid_count} qarzdor)"

    info_text = (
        f"👤 <b>Foydalanuvchi ma'lumotlari:</b>\n\n"
        f"🆔 ID Kod: <b>{user.get('id_code') or 'Berilmagan'}</b>\n"
        f"📌 Holati: <b>{user.get('status')}</b>\n"
        f"👤 Ism: {first_name_esc} {last_name_esc}\n"
        f"{cargos_stat}\n"
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
        reply_markup=user_card_actions_keyboard(user["user_id"], cargo_count)
    )

# --- USER CARGOS & REPORT MANAGEMENT (VIEW / EDIT / DELETE) ---
@admin_router.callback_query(F.data.startswith("user_cargos_"))
async def callback_user_cargos(query: CallbackQuery, bot: Bot):
    if not await check_admin_or_reject(query):
        return
    await query.answer()

    user_id = int(query.data.split("_")[2])
    user = await get_user(user_id)
    if not user:
        await query.message.answer("❌ Mijoz topilmadi.")
        return

    id_code = user.get("id_code", "")
    reports = await get_user_reports(id_code)

    first_name_esc = html.escape(user.get("first_name") or "")
    if not reports:
        await query.message.answer(
            f"📦 <b>{id_code} — {first_name_esc}</b> uchun hozircha yuborilgan yuk hisobotlari mavjud emas.",
            parse_mode="HTML",
            reply_markup=user_card_actions_keyboard(user_id)
        )
        return

    text = (
        f"📦 <b>{id_code} — {first_name_esc}</b> yuklar tarixi:\n"
        f"Jami yuborilgan foto-otchyotlar: <b>{len(reports)} ta</b>\n\n"
        f"<i>Tahrirlash yoki o'chirish uchun hisobotni tanlang:</i>"
    )
    await query.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=user_reports_list_keyboard(reports, user_id)
    )

@admin_router.callback_query(F.data.startswith("view_report_"))
async def callback_view_single_report(query: CallbackQuery, bot: Bot, state: FSMContext):
    if not await check_admin_or_reject(query):
        return
    await query.answer()
    await state.clear()

    parts = query.data.split("_")
    report_id = int(parts[2])
    user_id = int(parts[3])

    report = await get_report_by_id(report_id)
    if not report:
        await query.message.answer("❌ Ushbu hisobot topilmadi (o'chirilgan bo'lishi mumkin).")
        return

    id_code = report.get("id_code", "")
    full_name_esc = html.escape(report.get("full_name") or "")
    phone_esc = html.escape(report.get("phone") or "")
    track_esc = html.escape(report.get("track_codes") or "")
    weight = report.get("weight", 0.0)
    price_usd = report.get("price_usd", 0.0)
    price_uzs = report.get("price_uzs", 0)
    payment_status = report.get("payment_status", "qarzdor")
    status_text = "🟢 To'langan" if payment_status == "tolandi" else "🔴 Qarzdor (To'lanmagan)"
    created_at = report.get("created_at", "")

    text = (
        f"📦 <b>Yuk Hisoboti (#{report_id}):</b>\n\n"
        f"🆔 Mijoz: <b>{id_code}</b> ({full_name_esc})\n"
        f"📱 Telefon: {phone_esc}\n"
        f"📅 Sana: {created_at}\n"
        f"🔖 Trek-kodlar:\n<code>{track_esc}</code>\n\n"
        f"⚖️ Og'irlik: <b>{weight} kg</b>\n"
        f"💵 Narx ($): <b>${price_usd}</b>\n"
        f"🇺🇿 Narx (so'm): <b>{price_uzs:,} so'm</b>\n"
        f"💳 To'lov holati: <b>{status_text}</b>"
    )

    photo_file_id = report.get("photo_file_id")
    if photo_file_id:
        try:
            await query.message.answer_photo(
                photo=photo_file_id,
                caption=text,
                parse_mode="HTML",
                reply_markup=report_manage_keyboard(report_id, user_id)
            )
            return
        except Exception:
            pass

    await query.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=report_manage_keyboard(report_id, user_id)
    )

@admin_router.callback_query(F.data.startswith("edit_rep_weight_"))
async def callback_edit_rep_weight(query: CallbackQuery, state: FSMContext):
    if not await check_admin_or_reject(query):
        return
    await query.answer()

    parts = query.data.split("_")
    report_id = int(parts[3])
    user_id = int(parts[4])

    report = await get_report_by_id(report_id)
    if not report:
        await query.message.answer("❌ Hisobot topilmadi.")
        return

    await state.set_state(EditReportStates.entering_new_weight)
    await state.update_data(
        report_id=report_id,
        user_id=user_id,
        id_code=report.get("id_code", ""),
        track_codes=report.get("track_codes", ""),
        old_weight=report.get("weight", 0.0)
    )

    await query.message.answer(
        f"⚖️ <b>Og'irlikni o'zgartirish (#{report_id}):</b>\n\n"
        f"Hozirgi og'irlik: <b>{report.get('weight')} kg</b>\n\n"
        f"Iltimos, yangi og'irlikni (kg) kiriting (masalan: <code>3.5</code>):",
        parse_mode="HTML",
        reply_markup=cancel_edit_report_keyboard(report_id, user_id)
    )

async def sync_report_message_changes(bot: Bot, report_id: int, user_id: int, new_track_codes: str, new_weight: float, new_price_usd: float, new_price_uzs: int):
    """
    Tahrirlangan yuk hisobotini mijoz chatida va Telegram kanalda ham yangilaydi (edit caption).
    """
    report = await get_report_by_id(report_id)
    user = await get_user(user_id)
    if not user:
        return

    updated_caption = format_report_caption(
        user=user,
        track_codes=new_track_codes,
        weight=new_weight,
        price_usd=new_price_usd,
        price_uzs=new_price_uzs,
        is_preview=False
    )

    client_msg_id = report.get("client_msg_id") if report else None
    channel_msg_id = report.get("channel_msg_id") if report else None
    channel_chat_id = report.get("channel_chat_id") if report else None

    # 1. Mijoz xabarini yangilash
    client_edited = False
    if client_msg_id:
        try:
            await bot.edit_message_caption(
                chat_id=user_id,
                message_id=client_msg_id,
                caption=updated_caption,
                parse_mode="HTML"
            )
            client_edited = True
        except Exception as e:
            logger.warning(f"Mijoz xabarini edit qilishda xatolik: {e}")

    # Agar xabar edit qilinmasa (eski xabar yoki o'chirilgan bo'lsa), mijozga yangilanish xabari yuboramiz
    if not client_edited:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"🔄 <b>Hurmatli mijoz, yukingiz haqidagi ma'lumot yangilandi:</b>\n\n{updated_caption}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Mijozga yangilanish xabari yuborishda xatolik: {e}")

    # 2. Kanal xabarini yangilash
    if channel_msg_id and channel_chat_id:
        try:
            target_ch = int(channel_chat_id) if channel_chat_id.startswith("-") and channel_chat_id[1:].isdigit() else channel_chat_id
            await bot.edit_message_caption(
                chat_id=target_ch,
                message_id=channel_msg_id,
                caption=updated_caption,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Kanal xabarini edit qilishda xatolik: {e}")

async def sync_report_message_deletion(bot: Bot, report: dict, user_id: int):
    """
    O'chirilgan yuk hisobotini mijoz chatidan va Telegram kanaldan bildirishnomasiz o'chiradi (delete_message).
    """
    client_msg_id = report.get("client_msg_id")
    channel_msg_id = report.get("channel_msg_id")
    channel_chat_id = report.get("channel_chat_id")

    # 1. Mijoz chatidagi xabarni o'chirish (ovozsiz / bildirishnomasiz)
    if client_msg_id:
        try:
            await bot.delete_message(chat_id=user_id, message_id=client_msg_id)
        except Exception as e:
            logger.warning(f"Mijoz xabarini o'chirishda xatolik: {e}")

    # 2. Kanal postini o'chirish
    if channel_msg_id and channel_chat_id:
        try:
            target_ch = int(channel_chat_id) if channel_chat_id.startswith("-") and channel_chat_id[1:].isdigit() else channel_chat_id
            await bot.delete_message(chat_id=target_ch, message_id=channel_msg_id)
        except Exception as e:
            logger.warning(f"Kanal xabarini o'chirishda xatolik: {e}")

@admin_router.message(EditReportStates.entering_new_weight, F.text)
async def state_save_new_weight(message: Message, state: FSMContext, bot: Bot):
    if not await check_admin_or_reject(message):
        return

    val = message.text.strip().replace(",", ".")
    try:
        new_weight = float(val)
        if new_weight <= 0 or new_weight > 5000:
            raise ValueError()
        new_weight = round(new_weight, 2)
    except ValueError:
        await message.answer(
            "⚠️ Noto'g'ri qiymat! Iltimos, og'irlikni to'g'ri musbat sonda kiriting (masalan: <code>3.5</code>):",
            parse_mode="HTML"
        )
        return

    data = await state.get_data()
    report_id = data.get("report_id")
    user_id = data.get("user_id")
    id_code = data.get("id_code")
    track_codes = data.get("track_codes")

    rate = await get_current_usd_rate()
    price_usd = round(new_weight * DEFAULT_KG_PRICE, 2)
    price_uzs = int(round(price_usd * rate))

    # 1. Bazada yangilash
    await update_report_weight(report_id, new_weight, price_usd, price_uzs)

    # 2. Google Sheetsda yangilash
    await sheet_manager.update_cargo_report(
        id_code=id_code,
        old_track_codes=track_codes,
        new_weight=new_weight,
        new_price_usd=price_usd,
        new_price_uzs=price_uzs
    )

    # 3. Mijoz va kanal xabarlarini yangilash
    await sync_report_message_changes(bot, report_id, user_id, track_codes, new_weight, price_usd, price_uzs)

    await state.clear()
    await message.answer(
        f"✅ <b>Og'irlik va narx muvaffaqiyatli yangilandi!</b>\n\n"
        f"⚖️ Yangi og'irlik: <b>{new_weight} kg</b>\n"
        f"💵 Narx ($): <b>${price_usd}</b>\n"
        f"🇺🇿 Narx (so'm): <b>{price_uzs:,} so'm</b>\n\n"
        f"<i>Google Sheets, ma'lumotlar bazasi va mijoz/kanal xabarlarida yangilandi.</i>",
        parse_mode="HTML",
        reply_markup=report_manage_keyboard(report_id, user_id)
    )

@admin_router.callback_query(F.data.startswith("edit_rep_tracks_"))
async def callback_edit_rep_tracks(query: CallbackQuery, state: FSMContext):
    if not await check_admin_or_reject(query):
        return
    await query.answer()

    parts = query.data.split("_")
    report_id = int(parts[3])
    user_id = int(parts[4])

    report = await get_report_by_id(report_id)
    if not report:
        await query.message.answer("❌ Hisobot topilmadi.")
        return

    await state.set_state(EditReportStates.entering_new_tracks)
    await state.update_data(
        report_id=report_id,
        user_id=user_id,
        id_code=report.get("id_code", ""),
        old_tracks=report.get("track_codes", "")
    )

    await query.message.answer(
        f"🔖 <b>Trek-kodlarni tahrirlash (#{report_id}):</b>\n\n"
        f"Hozirgi trek-kodlar:\n<code>{html.escape(report.get('track_codes', ''))}</code>\n\n"
        f"Iltimos, yangi trek-kod(lar)ni kiriting (bir nechta bo'lsa probel yoki vergul bilan):",
        parse_mode="HTML",
        reply_markup=cancel_edit_report_keyboard(report_id, user_id)
    )

@admin_router.message(EditReportStates.entering_new_tracks, F.text)
async def state_save_new_tracks(message: Message, state: FSMContext, bot: Bot):
    if not await check_admin_or_reject(message):
        return

    raw_text = message.text.strip()
    raw_tokens = re.split(r'[\s,\n]+', raw_text)
    tracks = [t.strip().upper() for t in raw_tokens if t.strip()]
    if not tracks:
        await message.answer("⚠️ Iltimos, kamida bitta trek-kod kiriting:")
        return

    new_track_codes = ", ".join(tracks)
    data = await state.get_data()
    report_id = data.get("report_id")
    user_id = data.get("user_id")
    id_code = data.get("id_code")
    old_tracks = data.get("old_tracks")

    # 1. Bazada yangilash
    await update_report_track_codes(report_id, new_track_codes)

    # 2. Google Sheetsda yangilash
    await sheet_manager.update_cargo_report(
        id_code=id_code,
        old_track_codes=old_tracks,
        new_track_codes=new_track_codes
    )

    # 3. Mijoz va kanal xabarlarini yangilash
    rep = await get_report_by_id(report_id)
    rep_w = rep.get("weight", 0.0) if rep else 0.0
    rep_usd = rep.get("price_usd", 0.0) if rep else 0.0
    rep_uzs = rep.get("price_uzs", 0) if rep else 0
    await sync_report_message_changes(bot, report_id, user_id, new_track_codes, rep_w, rep_usd, rep_uzs)

    await state.clear()
    await message.answer(
        f"✅ <b>Trek-kod(lar) muvaffaqiyatli yangilandi!</b>\n\n"
        f"🔖 Yangi trek-kodlar:\n<code>{html.escape(new_track_codes)}</code>\n\n"
        f"<i>Google Sheets, ma'lumotlar bazasi va mijoz/kanal xabarlarida yangilandi.</i>",
        parse_mode="HTML",
        reply_markup=report_manage_keyboard(report_id, user_id)
    )

@admin_router.callback_query(F.data.startswith("del_rep_confirm_"))
async def callback_del_rep_confirm(query: CallbackQuery):
    if not await check_admin_or_reject(query):
        return
    await query.answer()

    parts = query.data.split("_")
    report_id = int(parts[3])
    user_id = int(parts[4])

    report = await get_report_by_id(report_id)
    if not report:
        await query.message.answer("❌ Hisobot topilmadi.")
        return

    await query.message.answer(
        f"⚠️ <b>Diqqat!</b>\n\n"
        f"Haqiqatan ham #{report_id} raqamli yuk hisobotini (Mijoz: <b>{report.get('id_code')}</b>, {report.get('weight')} kg) o'chirmoqchimisiz?\n\n"
        f"Bu amal hisobotni <b>bazadan va Google Sheetsdan butunlay o'chirib tashlaydi</b>.",
        parse_mode="HTML",
        reply_markup=report_delete_confirm_keyboard(report_id, user_id)
    )

@admin_router.callback_query(F.data.startswith("del_rep_do_"))
async def callback_del_rep_do(query: CallbackQuery, bot: Bot):
    if not await check_admin_or_reject(query):
        return
    await query.answer()

    parts = query.data.split("_")
    report_id = int(parts[3])
    user_id = int(parts[4])

    report = await get_report_by_id(report_id)
    if not report:
        await query.message.answer("❌ Hisobot allaqachon o'chirilgan.")
        return

    id_code = report.get("id_code", "")
    track_codes = report.get("track_codes", "")

    # 1. Mijoz va kanal postini o'chirish
    await sync_report_message_deletion(bot, report, user_id)

    # 2. Bazadan o'chirish
    await delete_report(report_id)

    # 3. Google Sheetsdan o'chirish
    await sheet_manager.delete_cargo_report(id_code, track_codes)

    await query.message.answer(
        f"🗑 <b>#{report_id} hisoboti muvaffaqiyatli o'chirildi!</b>\n"
        f"Baza, Google Sheets va Telegram xabarlaridan olib tashlandi.",
        parse_mode="HTML"
    )

    # Foydalanuvchi yuklari ro'yxatini qayta ko'rsatamiz
    user = await get_user(user_id)
    if user:
        reports = await get_user_reports(id_code)
        first_name_esc = html.escape(user.get("first_name") or "")
        if not reports:
            await query.message.answer(
                f"📦 <b>{id_code} — {first_name_esc}</b> uchun yuborilgan boshqa yuklar qolmadi.",
                parse_mode="HTML",
                reply_markup=user_card_actions_keyboard(user_id)
            )
        else:
            await query.message.answer(
                f"📦 <b>{id_code} — {first_name_esc}</b> yuklar tarixi:\n"
                f"Qolgan hisobotlar: <b>{len(reports)} ta</b>",
                parse_mode="HTML",
                reply_markup=user_reports_list_keyboard(reports, user_id)
            )



@admin_router.message(Command("backup"))
async def cmd_backup_database(message: Message):
    if not await check_admin_or_reject(message):
        return

    if not os.path.exists(DB_PATH):
        await message.answer("⚠️ Ma'lumotlar bazasi fayli topilmadi.")
        return

    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = FSInputFile(DB_PATH, filename=f"cargo_backup_{now_str}.db")
    await message.answer_document(
        document=backup_file,
        caption=(
            f"💾 <b>Ma'lumotlar bazasi zaxira nusxasi (Backup)</b>\n\n"
            f"📅 Vaqt: <code>{now_str}</code>\n\n"
            f"Ushbu fayl barcha mijozlar ro'yxati, arizalar va yuklar tarixini o'z ichiga oladi."
        ),
        parse_mode="HTML"
    )

@admin_router.message(Command("sync_sheets"))
async def cmd_sync_sheets(message: Message):
    if not await check_admin_or_reject(message):
        return

    if not sheet_manager.is_configured():
        await message.answer("⚠️ Google Sheets sozlanmagan! <code>credentials.json</code> faylini bot papkasiga joylashtiring.", parse_mode="HTML")
        return

    await message.answer("🔄 Google Sheets bilan ikki tomonlama to'liq sinxronizatsiya boshlandi...")

    # 1. Sheetsdan bazaga yangi mijozlar va yuklarni import qilish
    u_imp = await sheet_manager.import_all_users_to_db()
    c_imp = await sheet_manager.import_all_cargos_to_db()

    # 2. Bazadagi hali Sheetsga yozilmagan mijozlarni Sheetsga yuborish
    unsynced = await get_unsynced_users()
    push_count = 0
    for user in unsynced:
        ok, msg = await sheet_manager.append_user(user)
        if ok:
            await mark_as_synced(user["user_id"])
            push_count += 1

    await message.answer(
        f"✅ <b>Google Sheets sinxronizatsiyasi yakunlandi!</b>\n\n"
        f"📥 Sheetsdan bazaga tiklandi: <b>{u_imp} ta mijoz, {c_imp} ta yuk</b>\n"
        f"📤 Bazadan Sheetsga yozildi: <b>{push_count} ta mijoz</b>\n\n"
        f"Barcha ma'lumotlar 100% Google Sheets bilan to'liq mos holatda!",
        parse_mode="HTML"
    )

# --- FOTO-OTCHYOT FSM FLOW ---
@admin_router.message(Command("otchyot"))
@admin_router.message(Command("report"))
@admin_router.callback_query(F.data == "admin_action_report")
async def start_report_entry(event: Message | CallbackQuery, state: FSMContext):
    if not await check_admin_or_reject(event):
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
    if not await check_admin_or_reject(query):
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
    if not await check_admin_or_reject(message):
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
    if not await check_admin_or_reject(message):
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
    if not await check_admin_or_reject(message):
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
    if not await check_admin_or_reject(message):
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
    if not await check_admin_or_reject(query):
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
    client_msg_id = None
    try:
        sent_user_msg = await bot.send_photo(
            chat_id=user["user_id"],
            photo=photo_file_id,
            caption=final_caption,
            parse_mode="HTML"
        )
        user_sent = True
        client_msg_id = sent_user_msg.message_id
    except Exception as e:
        logger.error(f"Foydalanuvchiga ({user.get('user_id')}) foto-otchyot yuborishda xatolik: {e}")
        user_err = str(e)

    # 2. Send to Telegram Channel (if connected)
    channel_id = await get_report_channel_id()
    channel_sent = False
    channel_err = ""
    channel_msg_id = None
    channel_chat_str = None
    if channel_id:
        try:
            target_ch = int(channel_id) if channel_id.startswith("-") and channel_id[1:].isdigit() else channel_id
            sent_ch_msg = await bot.send_photo(
                chat_id=target_ch,
                photo=photo_file_id,
                caption=final_caption,
                parse_mode="HTML"
            )
            channel_sent = True
            channel_msg_id = sent_ch_msg.message_id
            channel_chat_str = str(target_ch)
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
        "created_at": now_str,
        "client_msg_id": client_msg_id,
        "channel_msg_id": channel_msg_id,
        "channel_chat_id": channel_chat_str
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
    if not await check_admin_or_reject(event):
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

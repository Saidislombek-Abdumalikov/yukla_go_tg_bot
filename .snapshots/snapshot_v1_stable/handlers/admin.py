import logging
import html
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command

from config import (
    ADMIN_IDS,
    SUPPORT_ADMIN_USERNAME,
    WAREHOUSE_RECEIVER,
    WAREHOUSE_PHONE,
    format_warehouse_address
)
from database import (
    get_user,
    get_user_by_id_code,
    approve_user_atomic,
    reject_user_atomic,
    mark_as_synced,
    get_unsynced_users,
    get_stats
)
from sheets import sheet_manager
from keyboards import approved_user_menu, reapply_keyboard

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

# Admin Management Commands
@admin_router.message(Command("admin"))
@admin_router.message(Command("stat"))
async def cmd_admin_stats(message: Message):
    if not is_admin(message.from_user.id):
        return

    stats = await get_stats()
    sheets_ok = "✅ Sozlangan" if sheet_manager.is_configured() else "⚠️ Sozlanmagan (credentials.json yo'q)"

    text = (
        f"📊 <b>Yukla GO — Bot Statistikasi</b>\n\n"
        f"👥 Jami ro'yxatdan o'tganlar: <b>{stats['total']}</b>\n"
        f"✅ Tasdiqlanganlar (Approved): <b>{stats['approved']}</b>\n"
        f"⏳ Ko'rib chiqilmoqda (Pending): <b>{stats['pending']}</b>\n"
        f"❌ Rad etilganlar: <b>{stats['rejected']}</b>\n\n"
        f"📑 <b>Google Sheets:</b> {sheets_ok}\n\n"
        f"Buyruqlar:\n"
        f"/sync_sheets — Google Sheetsga sinxronlash\n"
        f"/user &lt;ID&gt; — Foydalanuvchi ma'lumoti va pasportini ko'rish (masalan: <code>/user YK1</code>)"
    )
    await message.answer(text, parse_mode="HTML")

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
    await message.answer(info_text, parse_mode="HTML")

    # Send passport photos if stored in bot
    front_id = user.get("passport_front_id")
    back_id = user.get("passport_back_id")

    if front_id:
        try:
            await bot.send_photo(
                chat_id=message.chat.id,
                photo=front_id,
                caption=f"🪪 Old tarafi: {first_name_esc} {last_name_esc}"
            )
        except Exception as e:
            logger.warning(f"Old pasport rasmini yuborishda xatolik: {e}")

    if back_id:
        try:
            await bot.send_photo(
                chat_id=message.chat.id,
                photo=back_id,
                caption=f"🪪 Orqa tarafi: {first_name_esc} {last_name_esc}"
            )
        except Exception as e:
            logger.warning(f"Orqa pasport rasmini yuborishda xatolik: {e}")

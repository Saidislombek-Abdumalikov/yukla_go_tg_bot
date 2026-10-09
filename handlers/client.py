import re
import os
import logging
import html
from aiogram import Router, F, Bot
from aiogram.types import Message, FSInputFile, ReplyKeyboardRemove
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from config import (
    TERMS_MESSAGE_1,
    TERMS_MESSAGE_2,
    TERMS_MESSAGE_3,
    SUPPORT_ADMIN_USERNAME,
    ADMIN_IDS,
    format_warehouse_address
)
from states import RegistrationStates
from keyboards import (
    terms_keyboard,
    region_keyboard,
    phone_keyboard,
    confirmation_keyboard,
    reapply_keyboard,
    approved_user_menu,
    admin_decision_keyboard
)
from database import (
    get_user,
    save_application
)
from sheets import sheet_manager

logger = logging.getLogger(__name__)
client_router = Router()

def normalize_phone(phone_text: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", phone_text)
    if cleaned.startswith("+998"):
        return cleaned
    if cleaned.startswith("998"):
        return "+" + cleaned
    if len(cleaned) == 9 and cleaned.isdigit():
        return "+998" + cleaned
    return cleaned

def is_valid_phone(phone_text: str) -> bool:
    pattern = r"^\+998\d{9}$"
    return bool(re.match(pattern, phone_text))

@client_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user = await get_user(user_id)

    if user and user.get("status") == "approved":
        id_code = user.get("id_code", "")
        china_addr_text = format_warehouse_address(id_code)
        text = (
            f"✅ <b>Tabriklaymiz! Siz tizimda ro'yxatdan o'tgansiz!</b>\n"
            f"🆔 Sizning ID kodingiz: <code>{id_code}</code>\n\n"
            f"{china_addr_text}\n\n"
            f"<blockquote>‼️ SKLAD KIRGIZGANINGIZDAN SO'NG SKRINSHOTINI TASHLAB BERING!\n"
            f"Sklad kirgizib va tekshirtirmay zakaz ursez u holatda biz yukizga javob bermaymiz\n\n"
            f"🔗 Endi siz ushbu id kodni adminga skrinshot qilib ko'rsatishingiz zarur</blockquote>"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=approved_user_menu())
        return

    if user and user.get("status") == "pending":
        await message.answer(
            "⏳ Arizangiz ko'rib chiqilmoqda. Iltimos, javobni kuting.",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    # If new user or previously rejected
    await show_terms_and_rules(message)

async def show_terms_and_rules(message: Message):
    # Message 1
    await message.answer(TERMS_MESSAGE_1, parse_mode="HTML")
    
    # Message 2
    await message.answer(TERMS_MESSAGE_2, parse_mode="HTML")
    
    # Message 3
    await message.answer(TERMS_MESSAGE_3, parse_mode="HTML")

    # Shartnoma file at the very end
    doc_path = "assets/shartnoma.docx"
    if os.path.exists(doc_path):
        try:
            doc_file = FSInputFile(doc_path, filename="Yukla_GO_Shartnoma.docx")
            await message.answer_document(
                doc_file,
                caption="📄 Yukla GO rasmiy xizmat ko'rsatish shartnomasi"
            )
        except Exception as e:
            logger.warning(f"Shartnoma faylini yuborishda xatolik: {e}")

    await message.answer(
        "<blockquote>Quyidagi shartnomani to'liq o'qib chiqing va rozi bo'lsangiz tasdiqlang:</blockquote>",
        parse_mode="HTML",
        reply_markup=terms_keyboard()
    )

@client_router.message(F.text == "🆔 Id Ko'd olish")
async def handle_reapply(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
    if user and user.get("status") == "approved":
        await message.answer("Siz allaqachon ro'yxatdan o'tgansiz! /start ni bosing.", reply_markup=approved_user_menu())
        return
    if user and user.get("status") == "pending":
        await message.answer("⏳ Arizangiz ko'rib chiqilmoqda. Iltimos, javobni kuting.", reply_markup=ReplyKeyboardRemove())
        return

    await message.answer(
        f"Bizning mijozimizga aylanish uchun avval Ishlash shartlari va qo'shimcha ma'lumotlar bilan tanishib chiqing, to'g'ri kelsa ro'yxatdan o'ting!\n\n"
        f"Agar tushunmasangiz admin bilan bog'laning: {SUPPORT_ADMIN_USERNAME}",
        reply_markup=ReplyKeyboardRemove()
    )
    await show_terms_and_rules(message)

@client_router.message(F.text == "✅ Roziman")
async def handle_terms_agree(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if user and user.get("status") == "approved":
        await message.answer("Siz allaqachon ro'yxatdan o'tgansiz! /start ni bosing.", reply_markup=approved_user_menu())
        return
    if user and user.get("status") == "pending":
        await message.answer("⏳ Arizangiz ko'rib chiqilmoqda. Iltimos, javobni kuting.", reply_markup=ReplyKeyboardRemove())
        return

    await state.set_state(RegistrationStates.choosing_region)
    await message.answer(
        "📍 Siz qayerda yashaysiz?",
        reply_markup=region_keyboard()
    )

@client_router.message(RegistrationStates.choosing_region)
async def handle_region(message: Message, state: FSMContext):
    region = message.text
    if not region or len(region.strip()) < 2:
        await message.answer("Iltimos, hududingizni tanlang yoki yozing:", reply_markup=region_keyboard())
        return

    await state.update_data(hudud=region.strip())
    await state.set_state(RegistrationStates.entering_phone)
    await message.answer(
        "📱 Telefon raqamingizni yuboring.\n\nQuyidagi tugmani bosing yoki +998XXXXXXXXX shaklida yozing.",
        reply_markup=phone_keyboard()
    )

@client_router.message(RegistrationStates.entering_phone, F.contact)
@client_router.message(RegistrationStates.entering_phone, F.text)
async def handle_phone(message: Message, state: FSMContext):
    if message.contact:
        phone = message.contact.phone_number
    else:
        phone = message.text

    phone = normalize_phone(phone)
    if not is_valid_phone(phone):
        await message.answer(
            "❗️ Noto'g'ri format! Telefon raqamni +998XXXXXXXXX shaklida yuboring yoki quyidagi tugmani bosing:",
            reply_markup=phone_keyboard()
        )
        return

    await state.update_data(phone=phone, extra_phone="")
    # Go directly to First Name (Qo'shimcha telefon so'ralmaydi)
    await state.set_state(RegistrationStates.entering_first_name)
    await message.answer(
        "👤 Ismingizni kiriting:",
        reply_markup=ReplyKeyboardRemove()
    )

@client_router.message(RegistrationStates.entering_first_name, F.text)
async def handle_first_name(message: Message, state: FSMContext):
    first_name = message.text.strip()
    if len(first_name) < 2:
        await message.answer("❗️ Ism kamida 2 ta harfdan iborat bo'lishi kerak. Qaytadan kiriting:")
        return

    await state.update_data(first_name=first_name)
    await state.set_state(RegistrationStates.entering_last_name)
    await message.answer("👤 Familiyangizni kiriting:")

@client_router.message(RegistrationStates.entering_last_name, F.text)
async def handle_last_name(message: Message, state: FSMContext):
    last_name = message.text.strip()
    if len(last_name) < 2:
        await message.answer("❗️ Familiya kamida 2 ta harfdan iborat bo'lishi kerak. Qaytadan kiriting:")
        return

    await state.update_data(last_name=last_name)
    await state.set_state(RegistrationStates.entering_passport)

    # 1st Photo: Sample Passport Series (AA0000001)
    sample_series_img = "assets/sample_passport_series.png"
    prompt_text = (
        "🪪 <b>Passport seriya raqamingizni kiriting:</b>\n\n"
        "Namuna yuqoridagi rasmdagi: <code>AA0000001</code>\n\n"
        "<blockquote>❗️ Eslatma: Hurmatli mijoz, agar passport yoki ID kartadagi seriya raqamingizni kiritmasangiz sizning so'rovingiz bekor qilinishi mumkin!</blockquote>"
    )
    if os.path.exists(sample_series_img):
        await message.answer_photo(
            FSInputFile(sample_series_img),
            caption=prompt_text,
            parse_mode="HTML"
        )
    else:
        await message.answer(prompt_text, parse_mode="HTML")

@client_router.message(RegistrationStates.entering_passport, F.text)
async def handle_passport(message: Message, state: FSMContext):
    passport = message.text.strip().upper().replace(" ", "")
    if not re.match(r"^[A-Z]{2}\d{7}$", passport):
        await message.answer(
            "❗️ Noto'g'ri pasport seriya raqami! Namuna: AA0000001 (2 ta harf va 7 ta raqam).\n"
            "Iltimos, qaytadan to'g'ri kiriting:"
        )
        return

    await state.update_data(passport_series=passport)
    await state.set_state(RegistrationStates.entering_pinfl)

    # 2nd Photo: Sample JShShIR / PINFL
    sample_pinfl_img = "assets/sample_pinfl.png"
    prompt_text = (
        "🪪 <b>Passport JShShIR(PINFL) raqamingizni kiriting:</b>\n\n"
        "Namuna yuqoridagi rasmdagi: <code>30101800050014</code>\n\n"
        "<blockquote>❗️ Eslatma: Hurmatli mijoz, agar passport yoki ID kartadagi JShShIR(Pinfl) raqamingizni kiritmasangiz sizning so'rovingiz bekor qilinishi mumkin!</blockquote>"
    )
    if os.path.exists(sample_pinfl_img):
        await message.answer_photo(
            FSInputFile(sample_pinfl_img),
            caption=prompt_text,
            parse_mode="HTML"
        )
    else:
        await message.answer(prompt_text, parse_mode="HTML")

@client_router.message(RegistrationStates.entering_pinfl, F.text)
async def handle_pinfl(message: Message, state: FSMContext):
    pinfl = message.text.strip().replace(" ", "")
    if not (pinfl.isdigit() and len(pinfl) == 14):
        await message.answer(
            "❗️ Noto'g'ri JShShIR! JShShIR 14 ta raqamdan iborat bo'lishi kerak.\n"
            "Namuna: 30101800050014\nQaytadan kiriting:"
        )
        return

    await state.update_data(pinfl=pinfl)
    await state.set_state(RegistrationStates.entering_address)
    await message.answer(
        "📍 <b>PRAPISKADAGI Yashash manzilingizni to'liq va to'g'ri kiriting:</b>\n\n"
        "<blockquote>Namuna: Toshkent shahri, Yunusobod tumani 10-kvartal, 65/4/45</blockquote>",
        parse_mode="HTML"
    )

@client_router.message(RegistrationStates.entering_address, F.text)
async def handle_address(message: Message, state: FSMContext):
    address = message.text.strip()
    if len(address) < 3:
        await message.answer("❗️ Iltimos, to'liq manzilingizni kiriting:")
        return

    await state.update_data(address=address)
    await state.set_state(RegistrationStates.uploading_front_photo)

    # 3rd Photo: Sample Front Photo
    sample_front_img = "assets/sample_front.png"
    prompt_text = (
        "🪪 <b>Passportingizni old tarafini yuklang (JShShIR va Seriya raqamini tasdiqlash uchun):</b>\n"
        "Namuna yuqoridagi rasmda\n\n"
        "<blockquote>‼️ Eslatma: Faqat O'zbekiston respublikasi biometrik passporti yoki ID Kartasi bo'lishi shart, aks holda sizning so'rovingiz qabul qilinmaydi!</blockquote>"
    )
    if os.path.exists(sample_front_img):
        await message.answer_photo(
            FSInputFile(sample_front_img),
            caption=prompt_text,
            parse_mode="HTML"
        )
    else:
        await message.answer(prompt_text, parse_mode="HTML")

@client_router.message(RegistrationStates.uploading_front_photo, F.photo)
async def handle_front_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(passport_front_id=photo_id)
    await state.set_state(RegistrationStates.uploading_back_photo)

    # 4th Photo: Sample Back Photo
    sample_back_img = "assets/sample_back.png"
    prompt_text = (
        "🪪 <b>Passportingizni orqa tarafini yuklang (JShShIR va Seriya raqamini tasdiqlash uchun):</b>\n"
        "Namuna yuqoridagi rasmda\n\n"
        "<blockquote>‼️ Eslatma: Faqat O'zbekiston respublikasi biometrik passporti yoki ID Kartasi bo'lishi shart, aks holda sizning so'rovingiz qabul qilinmaydi!</blockquote>"
    )
    if os.path.exists(sample_back_img):
        await message.answer_photo(
            FSInputFile(sample_back_img),
            caption=prompt_text,
            parse_mode="HTML"
        )
    else:
        await message.answer(prompt_text, parse_mode="HTML")

@client_router.message(RegistrationStates.uploading_front_photo)
async def handle_front_photo_invalid(message: Message):
    await message.answer("❗️ Iltimos, pasportning old tarafi rasmini (photo) yuboring!")

@client_router.message(RegistrationStates.uploading_back_photo, F.photo)
async def handle_back_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(passport_back_id=photo_id)
    await state.set_state(RegistrationStates.confirming_data)

    data = await state.get_data()
    fn_esc = html.escape(data.get('first_name', ''))
    ln_esc = html.escape(data.get('last_name', ''))
    addr_esc = html.escape(data.get('address', ''))
    hudud_esc = html.escape(data.get('hudud', ''))

    summary = (
        "📋 <b>Ma'lumotlaringizni tekshiring:</b>\n\n"
        f"📍 <b>Hudud:</b> {hudud_esc}\n"
        f"📱 <b>Telefon:</b> {data.get('phone')}\n"
        f"👤 <b>Ism:</b> {fn_esc}\n"
        f"👤 <b>Familiya:</b> {ln_esc}\n"
        f"🪪 <b>Pasport:</b> {data.get('passport_series')}\n"
        f"🔢 <b>JSHSHIR:</b> {data.get('pinfl')}\n"
        f"📍 <b>Manzil:</b> {addr_esc}"
    )
    await message.answer(summary, parse_mode="HTML", reply_markup=confirmation_keyboard())

@client_router.message(RegistrationStates.uploading_back_photo)
async def handle_back_photo_invalid(message: Message):
    await message.answer("❗️ Iltimos, pasportning orqa tarafi rasmini (photo) yuboring!")

@client_router.message(RegistrationStates.confirming_data, F.text == "🔄 Qaytadan kiritish")
async def handle_restart_registration(message: Message, state: FSMContext):
    await state.set_state(RegistrationStates.entering_phone)
    await message.answer(
        "📱 Telefon raqamingizni yuboring:",
        reply_markup=phone_keyboard()
    )

@client_router.message(RegistrationStates.confirming_data, F.text == "✅ Tasdiqlash")
async def handle_submit_application(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    data = await state.get_data()
    data["username"] = username

    # Save application to SQLite
    await save_application(user_id, data)
    try:
        await sheet_manager.save_or_update_user_application(user_id, data)
    except Exception as e:
        logger.warning(f"Sheetsga arizani saqlashda xatolik: {e}")
    await state.clear()

    # Inform user
    await message.answer(
        "✅ Arizangiz qabul qilindi! Admin ko'rib chiqgandan so'ng javob olasiz.",
        reply_markup=ReplyKeyboardRemove()
    )

    fn_esc = html.escape(data.get('first_name', ''))
    ln_esc = html.escape(data.get('last_name', ''))
    hudud_esc = html.escape(data.get('hudud', ''))
    addr_esc = html.escape(data.get('address', ''))
    user_esc = html.escape(username)

    # Send notification to admins
    admin_text = (
        f"🆕 <b>Yangi ro'yxatdan o'tish arizasi!</b>\n\n"
        f"👤 <b>Ism:</b> {fn_esc}\n"
        f"👤 <b>Familiya:</b> {ln_esc}\n"
        f"📍 <b>Hudud:</b> {hudud_esc}\n"
        f"📱 <b>Telefon:</b> {data.get('phone')}\n"
        f"🪪 <b>Pasport:</b> {data.get('passport_series')}\n"
        f"🔢 <b>JSHSHIR:</b> {data.get('pinfl')}\n"
        f"📍 <b>Manzil:</b> {addr_esc}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user_id}</code>\n"
        f"👤 <b>Username:</b> @{user_esc if user_esc else 'yo`q'}"
    )

    for admin_id in ADMIN_IDS:
        try:
            # Send Front Photo
            await bot.send_photo(
                chat_id=admin_id,
                photo=data.get("passport_front_id"),
                caption=f"🪪 Pasport OLD tarafi: {fn_esc} {ln_esc} ({user_id})"
            )
            # Send Back Photo with admin keyboard
            await bot.send_photo(
                chat_id=admin_id,
                photo=data.get("passport_back_id"),
                caption=admin_text,
                parse_mode="HTML",
                reply_markup=admin_decision_keyboard(user_id)
            )
        except Exception as e:
            logger.error(f"Adminga ({admin_id}) xabar yuborishda xatolik: {e}")

# Approved Menu Handlers
@client_router.message(F.text == "🆔 Mening ID kodim")
async def show_my_id(message: Message):
    user = await get_user(message.from_user.id)
    if user and user.get("status") == "approved":
        fn_esc = html.escape(user.get('first_name') or '')
        ln_esc = html.escape(user.get('last_name') or '')
        addr_esc = html.escape(user.get('address') or '')
        await message.answer(
            f"👤 <b>Foydalanuvchi:</b> {fn_esc} {ln_esc}\n"
            f"🆔 <b>Sizning ID kodingiz:</b> <code>{user.get('id_code')}</code>\n"
            f"📱 <b>Telefon:</b> {user.get('phone')}\n"
            f"📍 <b>Manzil:</b> {addr_esc}",
            parse_mode="HTML"
        )
    else:
        await message.answer("Siz hali tasdiqlanmagansiz. /start ni bosing.")

@client_router.message(F.text == "🇨🇳 Xitoy ombor manzili")
async def show_china_address(message: Message):
    user = await get_user(message.from_user.id)
    if user and user.get("status") == "approved":
        id_code = user.get("id_code", "")
        china_addr_text = format_warehouse_address(id_code)
        text = (
            f"{china_addr_text}\n\n"
            f"<blockquote>‼️ SKLAD KIRGIZGANINGIZDAN SO'NG SKRINSHOTINI TASHLAB BERING!\n"
            f"Sklad kirgizib va tekshirtirmay zakaz ursez u holatda biz yukizga javob bermaymiz\n\n"
            f"🔗 Endi siz ushbu id kodni adminga skrinshot qilib ko'rsatishingiz zarur</blockquote>"
        )
        await message.answer(text, parse_mode="HTML")
    else:
        await message.answer("Xitoy ombor manzili faqat tasdiqlangan mijozlarga taqdim etiladi.")

@client_router.message(F.text == "📋 Shartlar va Qoidalar")
async def show_rules_menu(message: Message):
    await message.answer(TERMS_MESSAGE_1, parse_mode="HTML")
    await message.answer(TERMS_MESSAGE_2, parse_mode="HTML")

@client_router.message(F.text == "📞 Admin bilan bog'lanish")
async def contact_admin(message: Message):
    await message.answer(
        f"Savollar yoki murojaatlar bo'lsa adminga yozishingiz mumkin:\n👉 {SUPPORT_ADMIN_USERNAME}"
    )


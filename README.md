# REAL CARGO — Telegram Bot (Google Sheets & ID Boshqaruvi)

Ushbu Telegram bot kargo kompaniyalari ("REAL CARGO") uchun yangi mijozlarni ro'yxatga olish, pasport va shaxsiy ma'lumotlarni tekshirish, admin tomonidan tasdiqlash/rad etish, noyob kargo ID kodi berish (masalan: `YK1`, `YK2`, `YK3`...) hamda tasdiqlangan ma'lumotlarni avtomatik **Google Sheets** jadvaliga kiritish uchun yaratilgan.

---

## 🌟 Asosiy Imkoniyatlar

1. **Avtomatik shartlar va ma'lumotlar:**
   - Foydalanuvchi `/start` bosganda AVTO KARGO shartlari, narxlari (1 kg — 6$, Gabarit — 7.5$), taqiqlangan mahsulotlar ro'yxati, UZPOST pochta yetkazib berish shartlari va rasmiy shartnoma hujjati (`.docx`) taqdim etiladi.
2. **Bosqichma-bosqich ro'yxatdan o'tish (FSM):**
   - Hudud tanlash (`Viloyat` / `Toshkent shahar`).
   - Asosiy telefon raqami (kontakt yuborish tugmasi yoki matn formatida `+998XXXXXXXXX`).
   - Qo'shimcha telefon raqami (birinchi raqamdan farqli bo'lishi tekshiriladi).
   - Ism va familiya.
   - Pasport seriya raqami (namuna: `AA0000001` rasmi bilan birga tekshiriladi).
   - Pasport JShShIR / PINFL raqami (14 ta raqamli tekshiruv).
   - Prapiskadagi to'liq yashash manzili.
   - Pasportning old va orqa tarafi rasmlari.
   - Foydalanuvchi ma'lumotlarini tekshirish va tasdiqlash (`✅ Tasdiqlash` / `🔄 Qaytadan kiritish`).
3. **Admin Moderatsiyasi (Tasdiqlash yoki Rad etish):**
   - Ma'lumotlar to'liq adminga yuboriladi (mijoz ma'lumotlari + pasport rasmlari).
   - Admin botning o'zida tugma orqali `✅ Tasdiqlash` yoki `❌ Rad etish`ni bosadi.
   - **Rad etilsa:** Foydalanuvchiga rad etilgani va `@nothing_related` orqali bog'lanish yoki `🆔 Id Ko'd olish` tugmasi chiqadi.
   - **Tasdiqlansa:**
     - Bot avtomatik navbatdagi ID kodni generatsiya qiladi (`YK1`, `YK2`, `YK3`...).
     - Google Sheets jadvaliga yangi qator qilib yozadi.
     - Foydalanuvchiga ID kodi va Xitoy ombor manzili (RC-554) to'liq yuboriladi.
4. **Pasport ma'lumotlari xavfsizligi:**
   - Pasport rasmlari va ma'lumotlari Telegram bot bazasida (`cargo.db`) xavfsiz saqlanadi.
   - Admin istalgan vaqtda `/user <ID>` buyrug'i orqali (masalan: `/user YK1`) mijoz ma'lumotlari va pasport rasmlarini ko'rishi mumkin.
5. **Google Sheets bilan ishonchli integratsiya:**
   - Agar Google Sheets sozlanmagan bo'lsa ham bot to'xtab qolmaydi, ma'lumotlarni SQLite bazasida saqlab turadi.
   - Admin `/sync_sheets` buyrug'i orqali istalgan payt sinxronlashi mumkin.

---

## 📁 Loyiha Strukturasi

```text
TGBOT/
├── assets/
│   ├── sample_passport_front.png   # Pasport old tarafi namunasi
│   ├── sample_passport_back.png    # Pasport orqa tarafi namunasi
│   └── shartnoma.docx              # REAL CARGO shartnoma hujjati
├── handlers/
│   ├── __init__.py                 # Routerlarni ro'yxatga olish
│   ├── client.py                   # Mijozlar uchun muloqot va ro'yxatdan o'tish
│   └── admin.py                    # Admin moderatsiyasi va buyruqlari
├── config.py                       # Sozlamalar va doimiy matnlar
├── database.py                     # SQLite ma'lumotlar bazasi
├── sheets.py                       # Google Sheets integratsiyasi
├── states.py                       # Aiogram FSM holatlari
├── keyboards.py                    # Barcha tugmalar (reply & inline)
├── main.py                         # Botni ishga tushiruvchi asosiy fayl
├── requirements.txt                # Kerakli Python kutubxonalari
├── .env.example                    # Sozlamalar namunasi
├── .env                            # Sizning shaxsiy sozlamalaringiz
└── README.md                       # Qo'llanma
```

---

## 🚀 Ishga Tushirish Bo'yicha Qo'llanma

### 1. Telegram Bot Tokenini Olish
1. Telegramda [@BotFather](https://t.me/BotFather) ga kiring.
2. `/newbot` buyrug'ini yuboring va botingiz nomini tanlang.
3. BotFather bergan tokenni nusxalab oling (masalan: `7123456789:AAH...`).

### 2. O'z Telegram ID Raqamingizni Olish
1. Telegramda [@userinfobot](https://t.me/userinfobot) ga kiring va `/start` bosing.
2. `Id:` qarshisidagi sonni oling (masalan: `543219876`).

### 3. `.env` Faylini To'ldirish
Loyiha papkasidagi `.env` faylini oching va ma'lumotlarni kiriting:

```env
BOT_TOKEN=7123456789:AAH...sizning_bot_tokeningiz
ADMIN_IDS=543219876
SUPPORT_ADMIN_USERNAME=@nothing_related
CREDENTIALS_FILE=credentials.json
GOOGLE_SHEET_NAME=REAL CARGO - Mijozlar
ID_PREFIX=YK
```

> **Eslatma:** Agar bir nechta admin bo'lsa, `ADMIN_IDS` ga vergul bilan ajratib yozing: `ADMIN_IDS=12345678,98765432`.

---

### 4. Google Sheets Ni Ulash (Juda Oson)

Google Sheets bilan integratsiya qilish uchun:

1. [Google Cloud Console](https://console.cloud.google.com/) saytiga kiring.
2. Yangi loyiha yarating (masalan: `RealCargoBot`).
3. **APIs & Services > Library** bo'limidan quyidagi 2 ta API ni yoqing (Enable):
   - **Google Sheets API**
   - **Google Drive API**
4. **APIs & Services > Credentials** bo'limiga o'ting:
   - **Create Credentials > Service account** ni bosing.
   - Istalgan nom bering va **Create and Continue** bosing.
5. Yaratilgan Service account ustiga bosing, **Keys** bo'limiga o'ting:
   - **Add Key > Create new key > JSON** ni tanlang va yuklab oling.
6. Yuklab olingan fayl nomini `credentials.json` deb o'zgartiring va ushbu `TGBOT` papkasiga tashlang.
7. [Google Sheets](https://sheets.google.com) ga kiring va yangi jadval oching:
   - Jadval nomini `.env` dagi `GOOGLE_SHEET_NAME` bilan bir xil qiling (masalan: `REAL CARGO - Mijozlar`).
   - Jadvalning o'ng yuqori qismidagi **Share (Поделиться)** tugmasini bosing va `credentials.json` ichidagi `client_email` manziliga (masalan: `cargo-bot@...iam.gserviceaccount.com`) **Editor (Редактор)** ruxsatini bering.

---

### 5. Botni Ishga Tushirish

Terminalda yoki buyruqlar satrida quyidagilarni bajaring:

```bash
# Agar kutubxonalar o'rnatilmagan bo'lsa:
pip install -r requirements.txt

# Botni ishga tushirish:
python main.py
```

---

## 🛠 Admin Buyruqlari

Adminlar botda quyidagi maxsus buyruqlardan foydalana oladilar:

- `/admin` yoki `/stat` — Ro'yxatdan o'tganlar, tasdiqlanganlar va kutilayotganlar statistikasi hamda Google Sheets holati.
- `/sync_sheets` — Google Sheetsga hali yozilmagan barcha tasdiqlangan mijozlarni sinxronlash.
- `/user <ID>` — Foydalanuvchi ma'lumotlarini qidirish va uning pasport rasmlarini ko'rish (Masalan: `/user YK1` yoki `/user 543219876`).

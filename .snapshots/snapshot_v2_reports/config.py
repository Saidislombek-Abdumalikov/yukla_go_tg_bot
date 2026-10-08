import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Admin Telegram IDs (comma-separated, e.g., 5059829001)
admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(i.strip()) for i in admin_ids_str.split(",") if i.strip().isdigit()]

# Google Sheets Configuration
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Yukla GO - Mijozlar")

# Support Admin Username
SUPPORT_ADMIN_USERNAME = os.getenv("SUPPORT_ADMIN_USERNAME", "@nothing_related")

# Database Path
DB_PATH = os.getenv("DB_PATH", "cargo.db")

# Payment Card Configuration
CARD_NUMBER = os.getenv("CARD_NUMBER", "9860170713411376")
CARD_HOLDER = os.getenv("CARD_HOLDER", "Abdumalikov Saidislombek")

# Pricing & Currency Settings
DEFAULT_USD_RATE = int(os.getenv("USD_RATE", "11800"))
DEFAULT_KG_PRICE = float(os.getenv("DEFAULT_KG_PRICE", "6.0"))

# Telegram Report Channel
REPORT_CHANNEL_ID = os.getenv("REPORT_CHANNEL_ID", "")
GOOGLE_SHEET_CARGOS_TAB = os.getenv("GOOGLE_SHEET_CARGOS_TAB", "Yuklar")

# Warehouse constants
WAREHOUSE_RECEIVER = "真RC-554"
WAREHOUSE_PHONE = "18922155990"
WAREHOUSE_RAW_ADDRESS = "广州市白云区龙归街道南村三姓十巷3号一楼档口 RC-554({id_code})"

def format_warehouse_address(id_code: str) -> str:
    addr = WAREHOUSE_RAW_ADDRESS.format(id_code=id_code)
    # Formatted all at once in one single copyable block with <code>
    return (
        f"🇨🇳 <b>Xitoydagi ombor manzili (nusxalash uchun ustiga bosing):</b>\n\n"
        f"<code>收货人: {WAREHOUSE_RECEIVER}\n"
        f"手机号码: {WAREHOUSE_PHONE}\n"
        f"{addr}</code>"
    )

# ID Prefix
ID_PREFIX = os.getenv("ID_PREFIX", "YK")

# Texts with Telegram blockquote tags
TERMS_MESSAGE_1 = """📋 <b>Ma'lumot va shartlar 🚚 AVTO KARGO</b>

🕒 Yetkazish muddati: 10–18 kun
📦 1 kg — 6$
📱 Gabarit: 7.5$
🚚 Haftasiga 2 ta reys
✅ Seriya urish — xohlaganingizcha (cheksiz)
❌ Pasport limiti umuman yo'q

<blockquote>YUKINGIZNI VILOYATLARDA UZPOST (Pochta) FILIALLARIGACHA USHBU BERILGAN TARIF ICHIDA YETQAZIB BERAMIZ!
‼️ AMMO BIR JO'NATMA UCHUN 10.000 SO'M TO'LOVI MAVJUD ‼️
Gabariti juda katta o'lchovli mahsulotlar alohida hisoblanadi (narx haqida ma'lumot olish uchun buyurtma berishdan oldin biz bilan maslahatlashingizni so'raymiz)</blockquote>"""

TERMS_MESSAGE_2 = """‼️ <b>AVTO YO'NALISHIDA TAQIQLANADI</b> ‼️

<blockquote>💍 Tilla va kumush buyumlari
📲 Turli ommaviy axborot vositalari (telefon, komputer, televizor, fleshka,) va ularning har qanday zapchastlari!
‼️ Sinuvchi har qanday buyumga
🧯 Yonuvchan mahsulotlar
🍴 Oziq-ovqat maxsulotlari
💉 Medetsinaga bog'liq har qanday tovar (dori darmon, med texnikalar)
❌ Linzalar
🙅‍♂️ Odam sog'lig'i uchun zararli mahsulotlar odamlarga ziyon berishi mumkin bo'lgan buyumlar
🪹 Urug' va ko'chatlar!
🔞 18+ va faxshni targ'ib qiluvchi buyumlar

Yuqorida ta'kidlab o'tilgan narsa va buyumlarni biz olib kirmaymiz!
Taqiqlangan buyum sotib olib qo'ysangiz, 7-kun saqlanadi va undan keyin javobgarlikni bo'ynimizga olmaymiz !!!</blockquote>

‼️ <b>MUHIM</b> ‼️
<blockquote>Yukingiz O'zbekistonga yetib kelgandan keyin omborda bepul saqlash kuni 3 kun.
3 kundan keyin kunlik 2$ jarima qo'shiladi.
5 kundan keyin yuk musodara qilinadi.</blockquote>"""

TERMS_MESSAGE_3 = """📦 <b>YETQAZIB BERISH XIZMATI HAQIDA</b>

Viloyatdagi mijozlarimiz yuklarini UZPOST pochtasi va Shaxsiy pochta orqali punkt manzillargacha bepul yetqazib beramiz,
‼️ <b>AMMO To'liqroq ma'lumotlar 👇</b>

<blockquote>1) BIR JO'NATMA UCHUN 10.000 SO'M TO'LOVI MAVJUD ‼️ Qolgan xarajatlar biz tomonimizdan!
2) Agar yukingiz 10-Kilogramdan oshsa uyingizgacha bepul yetqazib beriladi
3) Bepul yetqazib berish hozircha Toshkent shahar uchun amal qilmaydi!

Biz faqat UZPOST manzillargacha yetqazib beramiz, filiallarni ko'rish: @uzpostfillyal</blockquote>"""

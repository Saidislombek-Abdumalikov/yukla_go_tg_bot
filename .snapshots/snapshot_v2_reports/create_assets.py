import os
from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

os.makedirs("assets", exist_ok=True)

# 1. Create Sample Passport Front
img_front = Image.new("RGB", (800, 500), color=(235, 245, 255))
draw_f = ImageDraw.Draw(img_front)
# Card border
draw_f.rounded_rectangle([30, 30, 770, 470], radius=25, fill=(245, 250, 255), outline=(50, 100, 180), width=4)
# Header
draw_f.rectangle([30, 30, 770, 90], fill=(50, 100, 180))
draw_f.text((50, 45), "O'ZBEKISTON RESPUBLIKASI / REPUBLIC OF UZBEKISTAN", fill=(255, 255, 255))
draw_f.text((50, 65), "SHAXSINI TASDIQ LOVCHI ID-KARTA (NAMUNA)", fill=(200, 230, 255))

# Photo placeholder
draw_f.rectangle([60, 120, 240, 360], fill=(210, 225, 240), outline=(100, 130, 160), width=2)
draw_f.text((110, 230), "[ SURAT ]", fill=(100, 120, 140))

# Fields
draw_f.text((270, 120), "Familiyasi / Surname: ABDUMALIKOV", fill=(30, 30, 30))
draw_f.text((270, 160), "Ismi / Given names: SAIDISLOM", fill=(30, 30, 30))
draw_f.text((270, 200), "Tug'ilgan sanasi: 01.01.2000", fill=(30, 30, 30))
draw_f.text((270, 240), "Jinsi / Sex: M", fill=(30, 30, 30))

# Highlight Passport Series
draw_f.rectangle([265, 280, 550, 330], fill=(255, 245, 200), outline=(230, 120, 0), width=2)
draw_f.text((275, 290), "👉 SERIYA RAQAMI: AA0000001", fill=(200, 50, 0))

# Highlight PINFL / JSHSHIR
draw_f.rectangle([265, 345, 650, 395], fill=(255, 245, 200), outline=(230, 120, 0), width=2)
draw_f.text((275, 355), "👉 JShShIR (PINFL): 30101800050014 (14 ta raqam)", fill=(200, 50, 0))

# Footer
draw_f.text((60, 420), "NAMUNA: Iltimos, seriya va JShShIR raqamingizni aniq tekshiring!", fill=(100, 100, 100))

img_front.save("assets/sample_passport_front.png")

# 2. Create Sample Passport Back
img_back = Image.new("RGB", (800, 500), color=(240, 245, 250))
draw_b = ImageDraw.Draw(img_back)
# Card border
draw_b.rounded_rectangle([30, 30, 770, 470], radius=25, fill=(250, 252, 255), outline=(50, 100, 180), width=4)
# Header
draw_b.rectangle([30, 30, 770, 90], fill=(60, 110, 170))
draw_b.text((50, 50), "IDENTIFIKATSIYA ID KARTASI - ORQA TARAFI (NAMUNA)", fill=(255, 255, 255))

draw_b.text((60, 130), "Kim tomonidan berilgan: IIB", fill=(30, 30, 30))
draw_b.text((60, 170), "Berilgan sanasi: 01.01.2021", fill=(30, 30, 30))
draw_b.text((60, 210), "Amal qilish muddati: 01.01.2031", fill=(30, 30, 30))

# Machine readable zone (MRZ)
draw_b.rectangle([60, 280, 740, 420], fill=(230, 235, 240), outline=(150, 160, 170), width=1)
draw_b.text((80, 300), "I<UZBAA00000018<<<<<<<<<<<<<<<", fill=(50, 50, 50))
draw_b.text((80, 335), "0001010M3101011UZB30101800050014<2", fill=(50, 50, 50))
draw_b.text((80, 370), "ABDUMALIKOV<<SAIDISLOM<<<<<<<<<", fill=(50, 50, 50))

img_back.save("assets/sample_passport_back.png")

# 3. Create shartnoma.docx
doc = Document()
doc.add_heading("Yukla GO — XIZMAT KO'RSATISH SHARTNOMASI VA QOIDALARI", level=1)

p_intro = doc.add_paragraph()
p_intro.add_run(
    "Yukla GO kompaniyamizni tashuvchi sifatida tanlaganingiz uchun hurmat va minnatdorchiligimizni bildiramiz. "
    "Iltimos, kompaniyaning quyidagi shartlari, talablari va narx siyosatini diqqat bilan o'qing.\n"
)

p1 = doc.add_paragraph()
p1.add_run("1. YUK TASHISH VA TARIFLAR:\n").bold = True
p1.add_run("• Yetkazish muddati: 10–18 kun\n")
p1.add_run("• Tarif: 1 kg — 6$\n")
p1.add_run("• Gabarit: 7.5$\n")
p1.add_run("• Haftasiga 2 ta reys\n")
p1.add_run("• Seriya urish cheksiz, pasport limiti umuman yo'q.\n")
p1.add_run("• Viloyatlarga UZPOST filiallarigacha yetkaziladi (har bir jo'natma uchun 10.000 so'm to'lov mavjud).\n\n")

p2 = doc.add_paragraph()
p2.add_run("2. TAQIQLANGAN MAHSULOTLAR RO'YXATI (AVTO YO'NALISHIDA):\n").bold = True
p2.add_run("• Tilla va kumush buyumlari\n")
p2.add_run("• Telefon, komputer, televizor, fleshka va har qanday elektronika zapchastlari\n")
p2.add_run("• Sinuvchi har qanday buyumlar\n")
p2.add_run("• Yonuvchan mahsulotlar\n")
p2.add_run("• Oziq-ovqat mahsulotlari\n")
p2.add_run("• Tibbiyotga bog'liq har qanday tovar (dori-darmon, med texnikalar)\n")
p2.add_run("• Linzalar\n")
p2.add_run("• Odam sog'lig'i uchun zararli bo'lgan mahsulotlar\n")
p2.add_run("• Urug' va ko'chatlar\n")
p2.add_run("• 18+ va fahshni targ'ib qiluvchi buyumlar\n\n")

p3 = doc.add_paragraph()
p3.add_run("3. OMBORDA SAQLASH VA JARIMALAR:\n").bold = True
p3.add_run("• O'zbekistonga yetib kelgach omborda bepul saqlash muddati: 3 kun.\n")
p3.add_run("• 3 kundan so'ng kunlik 2$ jarima qo'shiladi.\n")
p3.add_run("• 5 kundan ortiq olinmagan yuklar musodara qilinadi.\n\n")

p4 = doc.add_paragraph()
p4.add_run("4. TOVARLARNI TASHISH UCHUN QABUL QILISH SHARTLARI VA MAS'ULIYAT:\n").bold = True
p4.add_run(
    "Tashuvchining omboriga topshirilgan barcha tovarlar deformatsiyalanmagan asl qadoqda bo'lishi kerak.\n"
    "Yuk o'ziga xos xususiyatlarni hisobga olgan holda, tashish, yuklash va tushirish kabi normal ishlov berishda uning yaxlitligi va xavfsizligi ta'minlanadigan tarzda qadoqlanishi kerak.\n"
    "Tez buziladigan va issiqlik ta'siriga chidamli bo'lmagan (ya'ni tez buziladigan yoki qizib ketishdan eriydigan) tovarlarni etkazib berishda, qadoqlash turidan qat'i nazar, tashuvchi faqat tovarning tashqi xavfsizligi uchun javobgar bo'ladi, lekin o'ramning tarkibi uchun emas.\n"
    "Sinuvchi maxsulotlarni omborga jonatishda uni tashishda xavfsizligini yo'lda sinmasligini oldini olish uchun tovar qadog'ini chidamli qilinishi kerak.\n"
    "Yukla GO sizning yukingiz omborimizga yetkazib berilgandan keyingina javobgar hisoblanadi.\n"
    "Yukla GO faqatgina uning omboriga yetkazib berilgan maxsulotlarni yetkazib berish majburiyatiga ega.\n"
    "Yukla GO sizning buyurtma berishdan toki bizning omborimizga yetib kelgunga qadar bo'lgan har qanday vaziyat va masalalarga javobgar emas!!!\n\n"
)

p5 = doc.add_paragraph()
p5.add_run("5. FAVQULODDA VAZIYAT (FORS-MAJOR):\n").bold = True
p5.add_run(
    "Favqulotda vaziyat holatlari (fors-major holatlari) — karantin choralari (COVID-19 pandemiyasi), zilzilalar, ko'chkilar, bo'ronlar, qurg'oqchilik va boshqalar yoki ijtimoiy-iqtisodiy sharoitlar kabi tabiiy hodisalar natijasida yuzaga kelgan favqulodda, yengib bo'lmaydigan va oldindan aytib bo'lmaydigan holatlar (avia va avto reyslarni kechiktirilishi yoki taqiqlanishi, urush, bloklar, jamoat manfaatlarini ko'zlab import va eksportni taqiqlash va boshqalar), tashuvchining irodasi va harakatlaridan qat'i nazar, bu bilan bog'liq holda o'z zimmasiga olgan majburiyatlarni o'z vaqtida bajara olmasligi mumkin.\n"
    "Fors-major holatlari tufayli majburiyatlarni bajarish muddati ushbu holatlar va ularning oqibatlarining davomiyligiga teng muddatga uzaytirilishi mumkin. Bunday holda, yuk jo'natuvchi tashuvchiga mumkin bo'lgan yo'qotishlarni qoplash bo'yicha da'volarni qoplamaydi va kelish muddatidagi boʻlayotgan kechikishlar uchun hech qanday javobgarlikni zimmasiga olmaydi!!!\n"
)

doc.save("assets/shartnoma.docx")
print("Shartnoma updated with full text.")


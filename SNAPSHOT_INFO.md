# 📸 Snapshot: v1.0 — Stabil Ishchi Versiya (Yukla GO)

- **Sana:** 2026-10-08
- **Tavsif:** To'liq audit qilingan, xatolardan xoli, barqaror ishlayotgan versiya.
- **Xususiyatlari:**
  1. Yukla GO brendi
  2. Bitta telefon raqami (kontakt tugmasi orqali qulay so'rash)
  3. Pasport seriya (`sample_passport_series.png`) va JShShIR (`sample_pinfl.png`) namuna rasmlari
  4. Pasport old (`sample_front.png`) va orqa (`sample_back.png`) namuna rasmlari
  5. Telegram iqtibos (`<blockquote>`) formatlari
  6. Xitoy ombor manzili bitta bosishda to'liq nusxalanadigan (`<code>`) blokda
  7. Rasmiy `shartnoma.docx` oxirida yuboriladi (barcha qoidalar, qabul qilish shartlari va fors-major bilan)
  8. Google Sheets avtomatik sinxronizatsiyasi
  9. SQLite WAL rejimi, xavfsiz atomik tasdiqlash (`approve_user_atomic`), HTML belgilari himoyasi
  10. Render.com ga mos avtomatik port ochish tizimi

### 🔄 Qaytarish (Restore):
Agar biror yangi o'zgarish kiritilsa-yu, uni yoqtirmay qolsangiz va ushbu holatga qaytmoqchi bo'lsangiz:
- Menga shunchaki **"avvalgi snapshotga qayt"** deb yozishingiz mumkin;
- Yoki terminalda: `python restore_snapshot.py` buyrug'ini ishga tushirsangiz, barcha fayllar 1 soniyada shu holatga qaytadi.

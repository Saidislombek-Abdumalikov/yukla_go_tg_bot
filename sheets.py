import os
import json
import logging
import asyncio
import re
from typing import Optional, Tuple
import gspread
from google.oauth2.service_account import Credentials
from config import CREDENTIALS_FILE, GOOGLE_SHEET_NAME, GOOGLE_SHEET_CARGOS_TAB
from database import get_connection

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

USER_HEADERS = [
    "ID KOD",
    "Ism",
    "Familiya",
    "Telefon",
    "Qo'shimcha tel",
    "Hudud",
    "Manzil",
    "Pasport seriya",
    "JShShIR (PINFL)",
    "Telegram ID",
    "Username",
    "Tasdiqlangan sana",
    "Holat",
    "Ariza sanasi",
    "Pasport old rasm ID",
    "Pasport orqa rasm ID"
]

CARGO_HEADERS = [
    "Sana",
    "ID KOD",
    "Ism",
    "Familiya",
    "Telefon",
    "Hudud",
    "Trek-kod(lar)",
    "Og'irlik (kg)",
    "Kargo narxi ($)",
    "Kargo narxi (so'm)",
    "To'lov holati",
    "UID",
    "Rasm ID",
    "Mijoz xabar ID",
    "Kanal xabar ID",
    "Kanal chat ID"
]

SETTINGS_HEADERS = [
    "Kalit",
    "Qiymat"
]
GOOGLE_SHEET_SETTINGS_TAB = "Sozlamalar"

class ImportResult(int):
    """
    Backwards-compatible integer that can also be unpacked as (success, count, msg).
    """
    def __new__(cls, count: int, success: bool = True, msg: str = ""):
        obj = super().__new__(cls, count)
        obj.success = success
        obj.count = count
        obj.msg = msg
        return obj

    def __iter__(self):
        return iter((self.success, self.count, self.msg))

class GoogleSheetManager:
    def __init__(self):
        self._gc: Optional[gspread.Client] = None
        self._lock = asyncio.Lock()

    def is_configured(self) -> bool:
        return (
            bool(os.getenv("GOOGLE_CREDENTIALS_JSON"))
            or os.path.exists(CREDENTIALS_FILE)
            or os.path.exists("/etc/secrets/credentials.json")
        )

    def _get_client_sync(self) -> gspread.Client:
        if self._gc is None:
            raw_creds = os.getenv("GOOGLE_CREDENTIALS_JSON")
            if raw_creds:
                info = json.loads(raw_creds)
                credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
            else:
                cred_path = CREDENTIALS_FILE
                if not os.path.exists(cred_path) and os.path.exists("/etc/secrets/credentials.json"):
                    cred_path = "/etc/secrets/credentials.json"
                credentials = Credentials.from_service_account_file(
                    cred_path,
                    scopes=SCOPES
                )
            self._gc = gspread.authorize(credentials)
        return self._gc

    def _get_spreadsheet_sync(self) -> gspread.Spreadsheet:
        if not self.is_configured():
            raise FileNotFoundError(f"Google credentials topilmadi ('{CREDENTIALS_FILE}' yoki GOOGLE_CREDENTIALS_JSON)!")

        gc = self._get_client_sync()
        sheet_id = os.getenv("GOOGLE_SHEET_ID")
        if sheet_id:
            try:
                return gc.open_by_key(sheet_id)
            except Exception as e:
                logger.error(f"Google Sheet ID '{sheet_id}' orqali ochilmadi: {e}")
                raise

        try:
            return gc.open(GOOGLE_SHEET_NAME)
        except gspread.SpreadsheetNotFound:
            logger.error(f"Google Sheet '{GOOGLE_SHEET_NAME}' topilmadi!")
            raise FileNotFoundError(f"Google Sheet '{GOOGLE_SHEET_NAME}' topilmadi yoki xizmat hisobiga ruxsat berilmagan!")

    def _get_users_worksheet_sync(self) -> gspread.Worksheet:
        sh = self._get_spreadsheet_sync()
        worksheet = sh.sheet1
        existing_rows = worksheet.get_all_values()
        if not existing_rows or not existing_rows[0]:
            worksheet.append_row(USER_HEADERS)
            logger.info("Foydalanuvchilar jadvali sarlavhalari yozildi.")
        elif len(existing_rows[0]) < len(USER_HEADERS):
            # Yangi ustunlar sarlavhalarini to'ldirish
            try:
                for idx in range(len(existing_rows[0]), len(USER_HEADERS)):
                    worksheet.update_cell(1, idx + 1, USER_HEADERS[idx])
            except Exception as e:
                logger.warning(f"Foydalanuvchilar sarlavhalarini yangilashda xatolik: {e}")
        return worksheet

    def _get_cargos_worksheet_sync(self) -> gspread.Worksheet:
        sh = self._get_spreadsheet_sync()
        try:
            ws = sh.worksheet(GOOGLE_SHEET_CARGOS_TAB)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=GOOGLE_SHEET_CARGOS_TAB, rows=1000, cols=len(CARGO_HEADERS) + 2)
            logger.info(f"'{GOOGLE_SHEET_CARGOS_TAB}' nomli yangi varaq yaratildi.")

        existing_rows = ws.get_all_values()
        if not existing_rows or not existing_rows[0]:
            ws.append_row(CARGO_HEADERS)
            logger.info("Yuklar jadvali sarlavhalari yozildi.")
        elif len(existing_rows[0]) < len(CARGO_HEADERS):
            try:
                for idx in range(len(existing_rows[0]), len(CARGO_HEADERS)):
                    ws.update_cell(1, idx + 1, CARGO_HEADERS[idx])
            except Exception as e:
                logger.warning(f"Yuklar jadvali sarlavhalarini yangilashda xatolik: {e}")
        return ws

    def _get_settings_worksheet_sync(self) -> gspread.Worksheet:
        sh = self._get_spreadsheet_sync()
        try:
            ws = sh.worksheet(GOOGLE_SHEET_SETTINGS_TAB)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=GOOGLE_SHEET_SETTINGS_TAB, rows=100, cols=5)
            logger.info(f"'{GOOGLE_SHEET_SETTINGS_TAB}' nomli yangi varaq yaratildi.")

        existing_rows = ws.get_all_values()
        if not existing_rows or not existing_rows[0]:
            ws.append_row(SETTINGS_HEADERS)
            logger.info("Sozlamalar jadvali sarlavhalari yozildi.")
        return ws

    async def save_setting_to_sheets(self, key: str, value: str) -> Tuple[bool, str]:
        if not self.is_configured():
            return False, f"Google credentials fayli '{CREDENTIALS_FILE}' mavjud emas."
        async with self._lock:
            try:
                loop = asyncio.get_running_loop()
                def _do_save():
                    ws = self._get_settings_worksheet_sync()
                    all_rows = ws.get_all_values()
                    key_clean = str(key).strip().lower()
                    target_row = None
                    for r_idx in range(1, len(all_rows)):
                        row = all_rows[r_idx]
                        if row and str(row[0]).strip().lower() == key_clean:
                            target_row = r_idx + 1
                            break
                    if target_row:
                        ws.update_cell(target_row, 2, str(value))
                    else:
                        ws.append_row([str(key), str(value)])
                    return True

                await asyncio.wait_for(loop.run_in_executor(None, _do_save), timeout=15.0)
                return True, "Sozlama saqlandi"
            except Exception as e:
                logger.error(f"Sheetsga sozlama saqlashda xatolik: {e}")
                self._gc = None
                return False, str(e)

    async def import_settings_from_sheets(self) -> ImportResult:
        if not self.is_configured():
            return ImportResult(0, False, "Google Sheets sozlanmagan")
        try:
            loop = asyncio.get_running_loop()
            def _fetch():
                ws = self._get_settings_worksheet_sync()
                return ws.get_all_values()
            rows = await asyncio.wait_for(loop.run_in_executor(None, _fetch), timeout=15.0)
            if len(rows) <= 1:
                return ImportResult(0, True, "Sozlamalar bo'sh")
            from database import set_setting
            imported = 0
            for row in rows[1:]:
                if len(row) >= 2 and row[0].strip():
                    await set_setting(row[0].strip(), row[1].strip())
                    imported += 1
            return ImportResult(imported, True, "Sozlamalar import qilindi")
        except Exception as e:
            logger.error(f"Sheetsdan sozlamalarni import qilishda xatolik: {e}")
            return ImportResult(0, False, str(e))

    async def save_or_update_user_application(self, user_id: int, user_data: dict) -> Tuple[bool, str]:
        """
        Saves or updates user application (pending, approved, rejected) without creating duplicates.
        Ensures phone, PINFL, and Telegram IDs preserve text precision.
        """
        if not self.is_configured():
            return False, f"Google credentials fayli '{CREDENTIALS_FILE}' mavjud emas."

        async with self._lock:
            try:
                loop = asyncio.get_running_loop()
                def _do_save():
                    ws = self._get_users_worksheet_sync()
                    all_rows = ws.get_all_values()
                    tg_id_str = str(user_id).strip()

                    pinfl_raw = str(user_data.get("pinfl") or "").strip()
                    pinfl_val = f"'{pinfl_raw}" if pinfl_raw and not pinfl_raw.startswith("'") else pinfl_raw

                    tg_id_val = f"'{tg_id_str}"

                    phone_raw = str(user_data.get("phone") or "").strip()
                    phone_val = f"'{phone_raw}" if phone_raw and not phone_raw.startswith("'") else phone_raw

                    extra_phone_raw = str(user_data.get("extra_phone") or "").strip()
                    extra_phone_val = f"'{extra_phone_raw}" if extra_phone_raw and not extra_phone_raw.startswith("'") else extra_phone_raw

                    status_val = str(user_data.get("status") or "pending").strip()
                    row_data = [
                        user_data.get("id_code", "") or "",
                        user_data.get("first_name", "") or "",
                        user_data.get("last_name", "") or "",
                        phone_val,
                        extra_phone_val,
                        user_data.get("hudud", "") or "",
                        user_data.get("address", "") or "",
                        user_data.get("passport_series", "") or "",
                        pinfl_val,
                        tg_id_val,
                        f"@{user_data.get('username')}" if user_data.get("username") else "",
                        user_data.get("approved_at", "") or "",
                        status_val,
                        user_data.get("created_at", "") or "",
                        user_data.get("passport_front_id", "") or "",
                        user_data.get("passport_back_id", "") or ""
                    ]

                    target_row_idx = None
                    for r_idx in range(1, len(all_rows)):
                        r = all_rows[r_idx]
                        if len(r) > 9:
                            existing_tg = str(r[9]).strip().lstrip("'")
                            if existing_tg == tg_id_str:
                                target_row_idx = r_idx + 1
                                break

                    if target_row_idx:
                        for col_idx, val in enumerate(row_data, start=1):
                            ws.update_cell(target_row_idx, col_idx, val)
                    else:
                        ws.append_row(row_data)
                    return True

                await asyncio.wait_for(loop.run_in_executor(None, _do_save), timeout=25.0)
                logger.info(f"Foydalanuvchi {user_id} Google Sheetsga saqlandi/yangilandi.")
                return True, "Muvaffaqiyatli saqlandi"
            except asyncio.TimeoutError:
                logger.error("Google Sheets user saqlashda timeout yuz berdi!")
                self._gc = None
                return False, "Google Sheets serveri javob bermadi (timeout)"
            except Exception as e:
                logger.error(f"Google Sheets user saqlashda xatolik: {e}")
                self._gc = None
                return False, str(e)

    async def append_user(self, user_data: dict) -> Tuple[bool, str]:
        """
        Appends or updates user data in Google Sheet with timeout protection.
        """
        user_id = user_data.get("user_id")
        if not user_id:
            # Fallback agar user_id berilmagan bo'lsa
            if not self.is_configured():
                return False, f"Google credentials fayli '{CREDENTIALS_FILE}' mavjud emas."
            async with self._lock:
                try:
                    loop = asyncio.get_running_loop()
                    def _do_append():
                        ws = self._get_users_worksheet_sync()
                        row = [
                            user_data.get("id_code", ""),
                            user_data.get("first_name", ""),
                            user_data.get("last_name", ""),
                            user_data.get("phone", ""),
                            user_data.get("extra_phone", ""),
                            user_data.get("hudud", ""),
                            user_data.get("address", ""),
                            user_data.get("passport_series", ""),
                            user_data.get("pinfl", ""),
                            str(user_data.get("user_id", "")),
                            f"@{user_data.get('username')}" if user_data.get("username") else "",
                            user_data.get("approved_at", ""),
                            user_data.get("status", "approved"),
                            user_data.get("created_at", ""),
                            user_data.get("passport_front_id", ""),
                            user_data.get("passport_back_id", "")
                        ]
                        ws.append_row(row)
                        return True
                    await asyncio.wait_for(loop.run_in_executor(None, _do_append), timeout=15.0)
                    return True, "Muvaffaqiyatli saqlandi"
                except Exception as e:
                    self._gc = None
                    return False, str(e)
        return await self.save_or_update_user_application(int(user_id), user_data)

    async def append_cargo(self, cargo_data: dict) -> Tuple[bool, str]:
        """
        Appends cargo report data to 'Yuklar' worksheet with full technical columns and timeout protection.
        """
        if not self.is_configured():
            return False, f"Google credentials fayli '{CREDENTIALS_FILE}' mavjud emas."

        async with self._lock:
            try:
                loop = asyncio.get_running_loop()
                def _do_append():
                    ws = self._get_cargos_worksheet_sync()
                    report_uid = str(cargo_data.get("report_uid") or "").strip()

                    # Idempotency tekshiruvi: report_uid bor bo'lsa tekshiramiz
                    if report_uid:
                        all_rows = ws.get_all_values()
                        for r in all_rows[1:]:
                            if len(r) > 11 and str(r[11]).strip() == report_uid:
                                logger.info(f"Yuk ({report_uid}) allaqachon Google Sheetsda mavjud.")
                                return True

                    price_usd = cargo_data.get("price_usd", 0)
                    price_uzs = cargo_data.get("price_uzs", 0)
                    payment_status = cargo_data.get("payment_status", "Qarzdor")
                    photo_file_id = str(cargo_data.get("photo_file_id") or "")
                    client_msg_id = str(cargo_data.get("client_msg_id") or "")
                    channel_msg_id = str(cargo_data.get("channel_msg_id") or "")
                    channel_chat_id = str(cargo_data.get("channel_chat_id") or "")

                    phone_raw = str(cargo_data.get("phone") or "").strip()
                    phone_val = f"'{phone_raw}" if phone_raw and not phone_raw.startswith("'") else phone_raw

                    row = [
                        cargo_data.get("created_at", ""),
                        cargo_data.get("id_code", ""),
                        cargo_data.get("first_name", ""),
                        cargo_data.get("last_name", ""),
                        phone_val,
                        cargo_data.get("hudud", ""),
                        cargo_data.get("track_codes", ""),
                        str(cargo_data.get("weight", "")),
                        f"{price_usd}$",
                        f"{price_uzs:,} so'm" if isinstance(price_uzs, (int, float)) else str(price_uzs),
                        payment_status,
                        report_uid,
                        photo_file_id,
                        client_msg_id,
                        channel_msg_id,
                        channel_chat_id
                    ]
                    ws.append_row(row)
                    return True

                await asyncio.wait_for(loop.run_in_executor(None, _do_append), timeout=20.0)
                logger.info(f"Yuk hisoboti ({cargo_data.get('id_code')}) Google Sheets 'Yuklar' varag'iga saqlandi.")
                return True, "Muvaffaqiyatli saqlandi"
            except asyncio.TimeoutError:
                logger.error("Google Sheets Yuklar varag'iga yozishda timeout yuz berdi!")
                # Timeout bo'lganda, report_uid orqali qo'shilganini tekshirish
                try:
                    report_uid = str(cargo_data.get("report_uid") or "").strip()
                    if report_uid:
                        ws = self._get_cargos_worksheet_sync()
                        all_rows = ws.get_all_values()
                        for r in all_rows[1:]:
                            if len(r) > 11 and str(r[11]).strip() == report_uid:
                                return True, "Muvaffaqiyatli saqlandi"
                except Exception:
                    pass
                self._gc = None
                return False, "Google Sheets serveri javob bermadi (timeout)"
            except Exception as e:
                logger.error(f"Google Sheets xatolik: {e}")
                self._gc = None
                return False, str(e)

    async def mark_cargos_paid(self, id_codes: list) -> Tuple[int, list]:
        """
        Updates 'To'lov holati' to 'To'landi' for specified id_codes in 'Yuklar' tab.
        """
        if not self.is_configured() or not id_codes:
            return 0, []

        target_set = {str(c).upper().strip() for c in id_codes if str(c).strip()}
        if not target_set:
            return 0, []

        async with self._lock:
            try:
                loop = asyncio.get_running_loop()
                def _do_update():
                    ws = self._get_cargos_worksheet_sync()
                    all_rows = ws.get_all_values()
                    if len(all_rows) < 2:
                        return 0, []

                    headers = all_rows[0]
                    id_col_idx = 1
                    status_col_idx = 10
                    for idx, h in enumerate(headers):
                        if "ID" in h.upper():
                            id_col_idx = idx
                        elif "TO'LOV" in h.upper() or "HOLAT" in h.upper():
                            status_col_idx = idx

                    updated_codes = []
                    for r_idx in range(1, len(all_rows)):
                        row = all_rows[r_idx]
                        if len(row) > id_col_idx:
                            row_id = str(row[id_col_idx]).upper().strip()
                            if row_id in target_set:
                                curr_status = row[status_col_idx] if len(row) > status_col_idx else ""
                                if curr_status != "To'landi":
                                    ws.update_cell(r_idx + 1, status_col_idx + 1, "To'landi")
                                    updated_codes.append(row_id)

                    return len(updated_codes), updated_codes

                res = await asyncio.wait_for(loop.run_in_executor(None, _do_update), timeout=25.0)
                logger.info(f"Google Sheetsda {res[0]} ta qator 'To'landi' ga o'zgartirildi.")
                return res
            except Exception as e:
                logger.error(f"Google Sheets to'lov holatini yangilashda xatolik: {e}")
                self._gc = None
                return 0, []

    async def update_cargo_report(
        self,
        id_code: str = None,
        old_track_codes: str = None,
        new_track_codes: str = None,
        new_weight: float = None,
        new_price_usd: float = None,
        new_price_uzs: int = None,
        report_uid: str = None
    ) -> Tuple[bool, str]:
        """
        Updates weight/prices or track_codes of a cargo row in 'Yuklar' worksheet.
        Matches by report_uid first, or exact track match. NO fallbacks to last row!
        """
        if not self.is_configured():
            return False, "Google credentials mavjud emas."
        async with self._lock:
            try:
                loop = asyncio.get_running_loop()
                def _do_update():
                    ws = self._get_cargos_worksheet_sync()
                    all_rows = ws.get_all_values()
                    if len(all_rows) < 2:
                        return False, "Jadval bo'sh"

                    target_row_idx = None
                    clean_uid = str(report_uid).strip() if report_uid else ""

                    # 1. Avvalo report_uid bo'yicha qidiramiz
                    if clean_uid:
                        for r_idx in range(len(all_rows) - 1, 0, -1):
                            row = all_rows[r_idx]
                            if len(row) > 11 and str(row[11]).strip() == clean_uid:
                                target_row_idx = r_idx + 1
                                break

                    # 2. Agar report_uid topilmasa va id_code/old_tracks berilgan bo'lsa:
                    # Qat'iy exact match (substring EMAS, oxirgi qatorga fallback EMAS!)
                    if not target_row_idx and id_code and old_track_codes:
                        id_clean = id_code.upper().strip()
                        old_tracks_clean = old_track_codes.strip().upper()
                        target_tokens = set(re.split(r'[\s,\n]+', old_tracks_clean)) - {""}

                        matching_rows = []
                        for r_idx in range(len(all_rows) - 1, 0, -1):
                            row = all_rows[r_idx]
                            if len(row) > 6:
                                row_id = str(row[1]).upper().strip()
                                row_tracks = str(row[6]).strip().upper()
                                row_tokens = set(re.split(r'[\s,\n]+', row_tracks)) - {""}
                                if row_id == id_clean and (row_tracks == old_tracks_clean or (target_tokens and row_tokens == target_tokens)):
                                    matching_rows.append(r_idx + 1)

                        if len(matching_rows) > 1:
                            return False, "Bir nechta mos yuk topildi (noaniq). Taxmin qilib o'zgartirish xavfsiz emas, amal to'xtatildi."
                        elif len(matching_rows) == 1:
                            target_row_idx = matching_rows[0]

                    if not target_row_idx:
                        return False, "Qator topilmadi"

                    if new_track_codes is not None:
                        ws.update_cell(target_row_idx, 7, str(new_track_codes))
                    if new_weight is not None:
                        ws.update_cell(target_row_idx, 8, str(new_weight))
                    if new_price_usd is not None:
                        ws.update_cell(target_row_idx, 9, f"{new_price_usd}$")
                    if new_price_uzs is not None:
                        ws.update_cell(target_row_idx, 10, f"{new_price_uzs:,} so'm")

                    return True, "Yangilandi"

                res, msg = await asyncio.wait_for(loop.run_in_executor(None, _do_update), timeout=25.0)
                return res, msg
            except Exception as e:
                logger.error(f"Google Sheetsda yukni tahrirlashda xatolik: {e}")
                self._gc = None
                return False, str(e)

    async def delete_cargo_report(self, id_code: str = None, track_codes: str = None, report_uid: str = None) -> Tuple[bool, str]:
        """
        Deletes matching cargo row from 'Yuklar' worksheet.
        Matches by report_uid first, or exact track match. NO fallback to last row!
        """
        if not self.is_configured():
            return False, "Google credentials mavjud emas."
        async with self._lock:
            try:
                loop = asyncio.get_running_loop()
                def _do_delete():
                    ws = self._get_cargos_worksheet_sync()
                    all_rows = ws.get_all_values()
                    if len(all_rows) < 2:
                        return False, "Jadval bo'sh"

                    target_row_idx = None
                    clean_uid = str(report_uid).strip() if report_uid else ""

                    # 1. report_uid bo'yicha qidirish
                    if clean_uid:
                        for r_idx in range(len(all_rows) - 1, 0, -1):
                            row = all_rows[r_idx]
                            if len(row) > 11 and str(row[11]).strip() == clean_uid:
                                target_row_idx = r_idx + 1
                                break

                    # 2. Agar UID bo'lmasa, exact match
                    if not target_row_idx and id_code and track_codes:
                        id_clean = id_code.upper().strip()
                        tracks_clean = track_codes.strip().upper()
                        target_tokens = set(re.split(r'[\s,\n]+', tracks_clean)) - {""}

                        matching_rows = []
                        for r_idx in range(len(all_rows) - 1, 0, -1):
                            row = all_rows[r_idx]
                            if len(row) > 6:
                                row_id = str(row[1]).upper().strip()
                                row_tracks = str(row[6]).strip().upper()
                                row_tokens = set(re.split(r'[\s,\n]+', row_tracks)) - {""}
                                if row_id == id_clean and (row_tracks == tracks_clean or (target_tokens and row_tokens == target_tokens)):
                                    matching_rows.append(r_idx + 1)

                        if len(matching_rows) > 1:
                            return False, "Bir nechta mos yuk topildi (noaniq). Taxmin qilib o'chirish xavfsiz emas, amal to'xtatildi."
                        elif len(matching_rows) == 1:
                            target_row_idx = matching_rows[0]

                    if not target_row_idx:
                        return False, "Google Sheetsda mos qator topilmadi"

                    ws.delete_rows(target_row_idx)
                    return True, "O'chirildi"

                res, msg = await asyncio.wait_for(loop.run_in_executor(None, _do_delete), timeout=25.0)
                return res, msg
            except Exception as e:
                logger.error(f"Google Sheetsda yukni o'chirishda xatolik: {e}")
                self._gc = None
                return False, str(e)

    async def import_all_users_to_db(self) -> ImportResult:
        """
        Google Sheetsdagi barcha mijozlarni o'qib, SQLite bazasiga import qiladi.
        Barcha holatlarni (pending, approved, rejected), sanalarni va rasm IDlarini tiklaydi.
        """
        if not self.is_configured():
            return ImportResult(0, False, "Google credentials mavjud emas")
        try:
            loop = asyncio.get_running_loop()
            def _fetch_rows():
                ws = self._get_users_worksheet_sync()
                return ws.get_all_values()

            rows = await asyncio.wait_for(loop.run_in_executor(None, _fetch_rows), timeout=20.0)
            if len(rows) <= 1:
                return ImportResult(0, True, "Foydalanuvchilar jadvali bo'sh")

            imported = 0
            async with get_connection() as db:
                for row in rows[1:]:
                    if not row or len(row) < 10:
                        continue
                    id_code = row[0].strip() if len(row) > 0 else ""
                    first_name = row[1].strip() if len(row) > 1 else ""
                    last_name = row[2].strip() if len(row) > 2 else ""
                    phone = row[3].strip().lstrip("'") if len(row) > 3 else ""
                    extra_phone = row[4].strip().lstrip("'") if len(row) > 4 else ""
                    hudud = row[5].strip() if len(row) > 5 else ""
                    address = row[6].strip() if len(row) > 6 else ""
                    passport_series = row[7].strip() if len(row) > 7 else ""
                    pinfl = row[8].strip().lstrip("'") if len(row) > 8 else ""
                    tg_id_str = row[9].strip().lstrip("'") if len(row) > 9 else ""
                    username = row[10].strip().lstrip("@") if len(row) > 10 else ""
                    approved_at = row[11].strip() if len(row) > 11 else ""

                    status = row[12].strip() if len(row) > 12 and row[12].strip() else ("approved" if id_code else "pending")
                    created_at = row[13].strip() if len(row) > 13 else ""
                    passport_front_id = row[14].strip() if len(row) > 14 else ""
                    passport_back_id = row[15].strip() if len(row) > 15 else ""

                    if not tg_id_str.isdigit():
                        continue
                    tg_id = int(tg_id_str)

                    cursor = await db.execute("""
                        INSERT INTO users (
                            user_id, username, hudud, phone, extra_phone,
                            first_name, last_name, passport_series, pinfl, address,
                            passport_front_id, passport_back_id, id_code, status,
                            created_at, approved_at, synced_to_sheets
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                        ON CONFLICT(user_id) DO UPDATE SET
                            username = excluded.username,
                            hudud = excluded.hudud,
                            phone = excluded.phone,
                            extra_phone = excluded.extra_phone,
                            first_name = excluded.first_name,
                            last_name = excluded.last_name,
                            passport_series = excluded.passport_series,
                            pinfl = excluded.pinfl,
                            address = excluded.address,
                            passport_front_id = COALESCE(NULLIF(excluded.passport_front_id, ''), users.passport_front_id),
                            passport_back_id = COALESCE(NULLIF(excluded.passport_back_id, ''), users.passport_back_id),
                            id_code = COALESCE(NULLIF(excluded.id_code, ''), users.id_code),
                            status = excluded.status,
                            created_at = COALESCE(NULLIF(excluded.created_at, ''), users.created_at),
                            approved_at = COALESCE(NULLIF(excluded.approved_at, ''), users.approved_at),
                            synced_to_sheets = 1
                    """, (
                        tg_id, username, hudud, phone, extra_phone,
                        first_name, last_name, passport_series, pinfl, address,
                        passport_front_id, passport_back_id, id_code if id_code else None,
                        status, created_at, approved_at
                    ))
                    if cursor.rowcount > 0:
                        imported += 1
                await db.commit()
            return ImportResult(imported, True, "Muvaffaqiyatli import qilindi")
        except Exception as e:
            logger.error(f"Google Sheetsdan bazaga import qilishda xatolik: {e}")
            return ImportResult(0, False, str(e))

    async def import_all_cargos_to_db(self) -> ImportResult:
        """
        Google Sheets 'Yuklar' varag'idagi barcha yuk hisobotlarini SQLite bazasiga import qiladi.
        Barcha maydonlarni (UID, rasm, Telegram xabar IDlari) tiklaydi.
        Sheets asosiy baza bo'lgani sababli Sheetsda yo'q bo'lgan yuklarni SQLite dan tozalaydi.
        """
        if not self.is_configured():
            return ImportResult(0, False, "Google credentials mavjud emas")
        try:
            loop = asyncio.get_running_loop()
            def _fetch_rows():
                ws = self._get_cargos_worksheet_sync()
                return ws.get_all_values()

            rows = await asyncio.wait_for(loop.run_in_executor(None, _fetch_rows), timeout=25.0)
            if len(rows) <= 1:
                return ImportResult(0, True, "Yuklar jadvali bo'sh")

            imported = 0
            valid_sheet_uids = set()

            async with get_connection() as db:
                for row in rows[1:]:
                    if not row or len(row) < 7:
                        continue
                    created_at = row[0].strip() if len(row) > 0 else ""
                    id_code = row[1].strip().upper() if len(row) > 1 else ""
                    first_name = row[2].strip() if len(row) > 2 else ""
                    last_name = row[3].strip() if len(row) > 3 else ""
                    full_name = f"{first_name} {last_name}".strip()
                    phone = row[4].strip().lstrip("'") if len(row) > 4 else ""
                    track_codes = row[6].strip() if len(row) > 6 else ""

                    try:
                        weight_raw = row[7].strip().replace(",", ".") if len(row) > 7 else "0"
                        weight = float(weight_raw) if weight_raw else 0.0
                    except Exception:
                        weight = 0.0

                    try:
                        raw_usd = row[8].replace("$", "").replace(",", ".").strip() if len(row) > 8 else "0"
                        price_usd = float(raw_usd) if raw_usd else 0.0
                    except Exception:
                        price_usd = 0.0

                    try:
                        raw_uzs = row[9].replace("so'm", "").replace(",", "").replace(" ", "").strip() if len(row) > 9 else "0"
                        price_uzs = int(raw_uzs) if raw_uzs and raw_uzs.isdigit() else 0
                    except Exception:
                        price_uzs = 0

                    status_raw = row[10].strip().lower() if len(row) > 10 else "qarzdor"
                    payment_status = "tolandi" if "to'landi" in status_raw or "tolandi" in status_raw else "qarzdor"

                    report_uid = row[11].strip() if len(row) > 11 else ""
                    photo_file_id = row[12].strip() if len(row) > 12 else ""
                    client_msg_id_raw = row[13].strip() if len(row) > 13 else ""
                    client_msg_id = int(client_msg_id_raw) if client_msg_id_raw.isdigit() else None
                    channel_msg_id_raw = row[14].strip() if len(row) > 14 else ""
                    channel_msg_id = int(channel_msg_id_raw) if channel_msg_id_raw.isdigit() else None
                    channel_chat_id = row[15].strip() if len(row) > 15 else ""

                    if not id_code or not track_codes:
                        continue

                    if report_uid:
                        valid_sheet_uids.add(report_uid)

                    async with db.execute("SELECT user_id FROM users WHERE UPPER(id_code) = ?", (id_code,)) as cur:
                        u_row = await cur.fetchone()
                        user_id = u_row[0] if u_row else None

                    exists = None
                    if report_uid:
                        async with db.execute("SELECT id FROM reports WHERE report_uid = ?", (report_uid,)) as cur:
                            exists = await cur.fetchone()

                    if not exists:
                        async with db.execute(
                            "SELECT id FROM reports WHERE UPPER(id_code) = ? AND track_codes = ? AND created_at = ?",
                            (id_code, track_codes, created_at)
                        ) as cur:
                            exists = await cur.fetchone()

                    if not exists:
                        if not report_uid:
                            import uuid
                            report_uid = f"rpt_{uuid.uuid4().hex[:12]}"
                            valid_sheet_uids.add(report_uid)

                        await db.execute("""
                            INSERT INTO reports (
                                user_id, id_code, full_name, phone, track_codes,
                                weight, price_usd, price_uzs, photo_file_id, payment_status, created_at,
                                client_msg_id, channel_msg_id, channel_chat_id, report_uid
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            user_id, id_code, full_name, phone, track_codes,
                            weight, price_usd, price_uzs, photo_file_id or None, payment_status, created_at,
                            client_msg_id, channel_msg_id, channel_chat_id or None, report_uid
                        ))
                        imported += 1
                    else:
                        rep_id = exists[0]
                        await db.execute("""
                            UPDATE reports SET
                                payment_status = ?,
                                photo_file_id = COALESCE(?, photo_file_id),
                                client_msg_id = COALESCE(?, client_msg_id),
                                channel_msg_id = COALESCE(?, channel_msg_id),
                                channel_chat_id = COALESCE(?, channel_chat_id),
                                report_uid = COALESCE(?, report_uid)
                            WHERE id = ?
                        """, (
                            payment_status,
                            photo_file_id or None,
                            client_msg_id,
                            channel_msg_id,
                            channel_chat_id or None,
                            report_uid or None,
                            rep_id
                        ))

                await db.commit()
            return ImportResult(imported, True, "Muvaffaqiyatli import qilindi")
        except Exception as e:
            logger.error(f"Google Sheetsdan yuklarni import qilishda xatolik: {e}")
            return ImportResult(0, False, str(e))

sheet_manager = GoogleSheetManager()

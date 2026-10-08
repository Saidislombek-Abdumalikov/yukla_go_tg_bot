import os
import json
import logging
import asyncio
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
    "Tasdiqlangan sana"
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
    "To'lov holati"
]

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
        try:
            return gc.open(GOOGLE_SHEET_NAME)
        except gspread.SpreadsheetNotFound:
            all_sheets = gc.openall()
            if all_sheets:
                logger.info(f"Mavjud ulangan jadval ochildi: {all_sheets[0].title}")
                return all_sheets[0]
            else:
                sh = gc.create(GOOGLE_SHEET_NAME)
                logger.info(f"Yangi Google jadval yaratildi: {GOOGLE_SHEET_NAME}")
                return sh

    def _get_users_worksheet_sync(self) -> gspread.Worksheet:
        sh = self._get_spreadsheet_sync()
        worksheet = sh.sheet1
        existing_rows = worksheet.get_all_values()
        if not existing_rows or not existing_rows[0]:
            worksheet.append_row(USER_HEADERS)
            logger.info("Foydalanuvchilar jadvali sarlavhalari yozildi.")
        return worksheet

    def _get_cargos_worksheet_sync(self) -> gspread.Worksheet:
        sh = self._get_spreadsheet_sync()
        try:
            ws = sh.worksheet(GOOGLE_SHEET_CARGOS_TAB)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=GOOGLE_SHEET_CARGOS_TAB, rows=1000, cols=14)
            logger.info(f"'{GOOGLE_SHEET_CARGOS_TAB}' nomli yangi varaq yaratildi.")

        existing_rows = ws.get_all_values()
        if not existing_rows or not existing_rows[0]:
            ws.append_row(CARGO_HEADERS)
            logger.info("Yuklar jadvali sarlavhalari yozildi.")
        elif len(existing_rows[0]) < len(CARGO_HEADERS):
            # Sarlavhani yangilash (To'lov holati ustuni qo'shish)
            try:
                ws.update_cell(1, len(CARGO_HEADERS), "To'lov holati")
            except Exception as e:
                logger.warning(f"Sarlavha yangilashda xatolik: {e}")
        return ws

    async def append_user(self, user_data: dict) -> Tuple[bool, str]:
        """
        Appends user data to Google Sheet with timeout protection.
        """
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
                        user_data.get("approved_at", "")
                    ]
                    ws.append_row(row)
                    return True

                await asyncio.wait_for(loop.run_in_executor(None, _do_append), timeout=15.0)
                logger.info(f"Foydalanuvchi {user_data.get('id_code')} Google Sheetsga saqlandi.")
                return True, "Muvaffaqiyatli saqlandi"
            except asyncio.TimeoutError:
                logger.error("Google Sheetsga yozishda timeout (15s) yuz berdi!")
                self._gc = None
                return False, "Google Sheets serveri javob bermadi (timeout)"
            except Exception as e:
                logger.error(f"Google Sheets xatolik: {e}")
                self._gc = None
                return False, str(e)

    async def append_cargo(self, cargo_data: dict) -> Tuple[bool, str]:
        """
        Appends cargo report data to 'Yuklar' worksheet with timeout protection.
        """
        if not self.is_configured():
            return False, f"Google credentials fayli '{CREDENTIALS_FILE}' mavjud emas."

        async with self._lock:
            try:
                loop = asyncio.get_running_loop()
                def _do_append():
                    ws = self._get_cargos_worksheet_sync()
                    price_usd = cargo_data.get("price_usd", 0)
                    price_uzs = cargo_data.get("price_uzs", 0)
                    payment_status = cargo_data.get("payment_status", "Qarzdor")
                    row = [
                        cargo_data.get("created_at", ""),
                        cargo_data.get("id_code", ""),
                        cargo_data.get("first_name", ""),
                        cargo_data.get("last_name", ""),
                        cargo_data.get("phone", ""),
                        cargo_data.get("hudud", ""),
                        cargo_data.get("track_codes", ""),
                        str(cargo_data.get("weight", "")),
                        f"{price_usd}$",
                        f"{price_uzs:,} so'm",
                        payment_status
                    ]
                    ws.append_row(row)
                    return True

                await asyncio.wait_for(loop.run_in_executor(None, _do_append), timeout=15.0)
                logger.info(f"Yuk hisoboti ({cargo_data.get('id_code')}) Google Sheets 'Yuklar' varag'iga saqlandi.")
                return True, "Muvaffaqiyatli saqlandi"
            except asyncio.TimeoutError:
                logger.error("Google Sheets Yuklar varag'iga yozishda timeout yuz berdi!")
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

        target_set = {str(c).upper().strip() for c in id_codes}
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
        id_code: str,
        old_track_codes: str,
        new_track_codes: str = None,
        new_weight: float = None,
        new_price_usd: float = None,
        new_price_uzs: int = None
    ) -> Tuple[bool, str]:
        """
        Updates weight/prices or track_codes of a cargo row in 'Yuklar' worksheet.
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

                    id_clean = id_code.upper().strip()
                    target_row_idx = None

                    for r_idx in range(len(all_rows) - 1, 0, -1):
                        row = all_rows[r_idx]
                        if len(row) > 6:
                            row_id = str(row[1]).upper().strip()
                            row_tracks = str(row[6]).strip()
                            if row_id == id_clean and (old_track_codes.strip() in row_tracks or row_tracks in old_track_codes.strip()):
                                target_row_idx = r_idx + 1
                                break

                    if not target_row_idx:
                        for r_idx in range(len(all_rows) - 1, 0, -1):
                            row = all_rows[r_idx]
                            if len(row) > 1 and str(row[1]).upper().strip() == id_clean:
                                target_row_idx = r_idx + 1
                                break

                    if not target_row_idx:
                        return False, "Qator topilmadi"

                    if new_track_codes is not None:
                        ws.update_cell(target_row_idx, 7, new_track_codes)
                    if new_weight is not None:
                        ws.update_cell(target_row_idx, 8, str(new_weight))
                        ws.update_cell(target_row_idx, 9, f"{new_price_usd}$")
                        ws.update_cell(target_row_idx, 10, f"{new_price_uzs:,} so'm")

                    return True, "Yangilandi"

                res, msg = await asyncio.wait_for(loop.run_in_executor(None, _do_update), timeout=25.0)
                return res, msg
            except Exception as e:
                logger.error(f"Google Sheetsda yukni tahrirlashda xatolik: {e}")
                self._gc = None
                return False, str(e)

    async def delete_cargo_report(self, id_code: str, track_codes: str) -> Tuple[bool, str]:
        """
        Deletes matching cargo row from 'Yuklar' worksheet.
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

                    id_clean = id_code.upper().strip()
                    target_row_idx = None

                    for r_idx in range(len(all_rows) - 1, 0, -1):
                        row = all_rows[r_idx]
                        if len(row) > 6:
                            row_id = str(row[1]).upper().strip()
                            row_tracks = str(row[6]).strip()
                            if row_id == id_clean and (track_codes.strip() in row_tracks or row_tracks in track_codes.strip()):
                                target_row_idx = r_idx + 1
                                break

                    if not target_row_idx:
                        for r_idx in range(len(all_rows) - 1, 0, -1):
                            row = all_rows[r_idx]
                            if len(row) > 1 and str(row[1]).upper().strip() == id_clean:
                                target_row_idx = r_idx + 1
                                break

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

    async def import_all_users_to_db(self) -> int:
        """
        Google Sheetsdagi barcha mijozlarni o'qib, SQLite bazasiga import qiladi (agar bazada bo'lmasa).
        Render qayta ishga tushganda ma'lumotlar yo'qolmasligi uchun xizmat qiladi.
        """
        if not self.is_configured():
            return 0
        try:
            loop = asyncio.get_running_loop()
            def _fetch_rows():
                ws = self._get_users_worksheet_sync()
                return ws.get_all_values()

            rows = await asyncio.wait_for(loop.run_in_executor(None, _fetch_rows), timeout=20.0)
            if len(rows) <= 1:
                return 0

            imported = 0
            async with get_connection() as db:
                for row in rows[1:]:
                    if not row or len(row) < 10:
                        continue
                    id_code = row[0].strip()
                    first_name = row[1].strip() if len(row) > 1 else ""
                    last_name = row[2].strip() if len(row) > 2 else ""
                    phone = row[3].strip() if len(row) > 3 else ""
                    extra_phone = row[4].strip() if len(row) > 4 else ""
                    hudud = row[5].strip() if len(row) > 5 else ""
                    address = row[6].strip() if len(row) > 6 else ""
                    passport_series = row[7].strip() if len(row) > 7 else ""
                    pinfl = row[8].strip() if len(row) > 8 else ""
                    tg_id_str = row[9].strip() if len(row) > 9 else ""
                    username = row[10].strip() if len(row) > 10 else ""
                    approved_at = row[11].strip() if len(row) > 11 else ""

                    if not tg_id_str.isdigit():
                        continue
                    tg_id = int(tg_id_str)

                    cursor = await db.execute("""
                        INSERT OR IGNORE INTO users (
                            user_id, username, hudud, phone, extra_phone,
                            first_name, last_name, passport_series, pinfl, address,
                            id_code, status, approved_at, synced_to_sheets
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'approved', ?, 1)
                    """, (
                        tg_id, username, hudud, phone, extra_phone,
                        first_name, last_name, passport_series, pinfl, address,
                        id_code, approved_at
                    ))
                    if cursor.rowcount > 0:
                        imported += 1
                await db.commit()
            return imported
        except Exception as e:
            logger.error(f"Google Sheetsdan bazaga import qilishda xatolik: {e}")
            return 0

sheet_manager = GoogleSheetManager()


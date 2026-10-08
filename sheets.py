import os
import logging
import asyncio
from typing import Optional, Tuple
import gspread
from google.oauth2.service_account import Credentials
from config import CREDENTIALS_FILE, GOOGLE_SHEET_NAME, GOOGLE_SHEET_CARGOS_TAB

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
        return os.path.exists(CREDENTIALS_FILE)

    def _get_client_sync(self) -> gspread.Client:
        if self._gc is None:
            credentials = Credentials.from_service_account_file(
                CREDENTIALS_FILE,
                scopes=SCOPES
            )
            self._gc = gspread.authorize(credentials)
        return self._gc

    def _get_spreadsheet_sync(self) -> gspread.Spreadsheet:
        if not self.is_configured():
            raise FileNotFoundError(f"Credentials fayli '{CREDENTIALS_FILE}' topilmadi!")

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

sheet_manager = GoogleSheetManager()

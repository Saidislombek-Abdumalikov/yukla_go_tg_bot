import os
import logging
import asyncio
from typing import Optional, Tuple
import gspread
from google.oauth2.service_account import Credentials
from config import CREDENTIALS_FILE, GOOGLE_SHEET_NAME

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

HEADERS = [
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

    def _get_worksheet_sync(self) -> gspread.Worksheet:
        if not self.is_configured():
            raise FileNotFoundError(f"Credentials fayli '{CREDENTIALS_FILE}' topilmadi!")

        gc = self._get_client_sync()
        
        try:
            sh = gc.open(GOOGLE_SHEET_NAME)
        except gspread.SpreadsheetNotFound:
            all_sheets = gc.openall()
            if all_sheets:
                sh = all_sheets[0]
                logger.info(f"Mavjud ulangan jadval ochildi: {sh.title}")
            else:
                sh = gc.create(GOOGLE_SHEET_NAME)
                logger.info(f"Yangi Google jadval yaratildi: {GOOGLE_SHEET_NAME}")

        worksheet = sh.sheet1
        
        # Check if headers exist
        existing_rows = worksheet.get_all_values()
        if not existing_rows or not existing_rows[0]:
            worksheet.append_row(HEADERS)
            logger.info("Jadval sarlavhalari (headers) yozildi.")
            
        return worksheet

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
                    ws = self._get_worksheet_sync()
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

                # 15 seconds timeout protection
                await asyncio.wait_for(loop.run_in_executor(None, _do_append), timeout=15.0)
                logger.info(f"Foydalanuvchi {user_data.get('id_code')} Google Sheetsga saqlandi.")
                return True, "Muvaffaqiyatli saqlandi"
            except asyncio.TimeoutError:
                logger.error("Google Sheetsga yozishda timeout (15s) yuz berdi!")
                self._gc = None # reset client
                return False, "Google Sheets serveri javob bermadi (timeout)"
            except Exception as e:
                logger.error(f"Google Sheets xatolik: {e}")
                self._gc = None # reset client on error
                return False, str(e)

sheet_manager = GoogleSheetManager()

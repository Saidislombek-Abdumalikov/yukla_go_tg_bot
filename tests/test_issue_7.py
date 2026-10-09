import unittest
from unittest.mock import MagicMock
import gspread

from sheets import GoogleSheetManager

class TestIssue7NoFallbackToRandomSpreadsheet(unittest.TestCase):
    def test_open_never_falls_back_to_random_sheets(self):
        sm = GoogleSheetManager()
        sm.is_configured = MagicMock(return_value=True)

        mock_gc = MagicMock()
        # Sozlangan jadval topilmasin
        mock_gc.open.side_effect = gspread.SpreadsheetNotFound()

        # Boshqa jadval mavjud bo'lsin
        other_spreadsheet = MagicMock()
        other_spreadsheet.title = "Boshqa_Notanish_Firma_Jadvali"
        mock_gc.openall.return_value = [other_spreadsheet]

        sm._get_client_sync = MagicMock(return_value=mock_gc)

        # Yangi kodda boshqa jadvalga o'tib ketmasdan, xato ko'tarilishi yoki None/xato bo'lishi kerak!
        # Eski kodda esa mock_gc.openall() chaqirilib, other_spreadsheet qaytib qoladi!
        with self.assertRaises((gspread.SpreadsheetNotFound, FileNotFoundError, ValueError)):
            sh = sm._get_spreadsheet_sync()
            # Agar eski kod boshqa jadvalni qaytarsa, bu yerda assert yiqiladi
            self.assertNotEqual(sh.title, "Boshqa_Notanish_Firma_Jadvali", "XAVF! Boshqa notanish jadvalga ulanib ketildi!")

if __name__ == "__main__":
    unittest.main()

import sqlite3
import gspread
from google.oauth2.service_account import Credentials
import config
import sheets

def reset_all():
    print("1. SQLite ma'lumotlar bazasini tozalash...")
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users")
    conn.commit()
    cursor.execute("VACUUM")
    conn.commit()
    conn.close()
    print("[OK] SQLite 'users' jadvalidagi barcha ma'lumotlar tozalandi (ID 1 dan boshlanadi).")

    print("\n2. Google Sheets jadvalini tozalash...")
    if sheets.sheet_manager.is_configured():
        try:
            creds = Credentials.from_service_account_file(
                config.CREDENTIALS_FILE,
                scopes=sheets.SCOPES
            )
            gc = gspread.authorize(creds)
            all_sheets = gc.openall()
            if all_sheets:
                sh = all_sheets[0]
                ws = sh.sheet1
                print(f"Topilgan jadval: '{sh.title}'")
                
                # Clear worksheet and re-add headers
                ws.clear()
                ws.append_row(sheets.HEADERS)
                print("[OK] Google Sheets jadvalidagi barcha mijozlar o'chirildi, faqat sarlavhalar qoldirildi.")
            else:
                print("[!] Ulangan jadval topilmadi.")
        except Exception as e:
            print(f"[!] Google Sheets tozalashda xatolik: {e}")
    else:
        print("[!] credentials.json topilmadi.")

    print("\n[SUCCESS] Barcha ma'lumotlar tozalandi! Endi yangidan toza (fresh) boshlanadi!")

if __name__ == "__main__":
    reset_all()

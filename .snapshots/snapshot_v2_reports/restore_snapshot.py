import os
import shutil

SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), ".snapshots", "snapshot_v1_stable")
ROOT_DIR = os.path.dirname(__file__)

FILES_TO_RESTORE = [
    "config.py",
    "database.py",
    "sheets.py",
    "states.py",
    "keyboards.py",
    "main.py",
    "requirements.txt",
    ".env",
    ".env.example",
    ".gitignore",
    "README.md",
    "reset_data.py"
]

DIRS_TO_RESTORE = [
    "handlers",
    "assets"
]

def restore():
    print("Snapshot v1 (barqaror versiya) tiklanmoqda...")
    if not os.path.exists(SNAPSHOT_DIR):
        print(f"Xatolik: Snapshot papkasi '{SNAPSHOT_DIR}' topilmadi!")
        return

    for file_name in FILES_TO_RESTORE:
        src = os.path.join(SNAPSHOT_DIR, file_name)
        dst = os.path.join(ROOT_DIR, file_name)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"[OK] {file_name} tiklandi.")

    for dir_name in DIRS_TO_RESTORE:
        src_dir = os.path.join(SNAPSHOT_DIR, dir_name)
        dst_dir = os.path.join(ROOT_DIR, dir_name)
        if os.path.exists(src_dir):
            if os.path.exists(dst_dir):
                shutil.rmtree(dst_dir)
            shutil.copytree(src_dir, dst_dir)
            print(f"[OK] {dir_name}/ papkasi tiklandi.")

    print("\n[SUCCESS] Bot to'liq v1 barqaror versiyaga qaytarildi!")

if __name__ == "__main__":
    restore()

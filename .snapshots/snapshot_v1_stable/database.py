import aiosqlite
import asyncio
import datetime
import logging
from contextlib import asynccontextmanager
from config import DB_PATH, ID_PREFIX

logger = logging.getLogger(__name__)

_approval_lock = asyncio.Lock()

@asynccontextmanager
async def get_connection():
    async with aiosqlite.connect(DB_PATH, timeout=10.0) as db:
        await db.execute("PRAGMA journal_mode = WAL;")
        await db.execute("PRAGMA busy_timeout = 5000;")
        db.row_factory = aiosqlite.Row
        yield db

async def init_db():
    async with get_connection() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                hudud TEXT,
                phone TEXT,
                extra_phone TEXT,
                first_name TEXT,
                last_name TEXT,
                passport_series TEXT,
                pinfl TEXT,
                address TEXT,
                passport_front_id TEXT,
                passport_back_id TEXT,
                id_code TEXT UNIQUE,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                approved_at TEXT,
                synced_to_sheets INTEGER DEFAULT 0
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_id_code ON users(id_code);")
        await db.commit()
    logger.info("Database initialized with WAL mode and indexes.")

async def get_user(user_id: int):
    async with get_connection() as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

async def get_user_by_id_code(id_code: str):
    async with get_connection() as db:
        async with db.execute("SELECT * FROM users WHERE id_code = ?", (id_code,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

async def save_application(user_id: int, data: dict):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with get_connection() as db:
        await db.execute("""
            INSERT INTO users (
                user_id, username, hudud, phone, extra_phone,
                first_name, last_name, passport_series, pinfl, address,
                passport_front_id, passport_back_id, status, created_at, synced_to_sheets
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, 0)
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
                passport_front_id = excluded.passport_front_id,
                passport_back_id = excluded.passport_back_id,
                status = 'pending',
                created_at = excluded.created_at,
                synced_to_sheets = 0
        """, (
            user_id,
            data.get("username", ""),
            data.get("hudud", ""),
            data.get("phone", ""),
            data.get("extra_phone", ""),
            data.get("first_name", ""),
            data.get("last_name", ""),
            data.get("passport_series", ""),
            data.get("pinfl", ""),
            data.get("address", ""),
            data.get("passport_front_id", ""),
            data.get("passport_back_id", ""),
            now
        ))
        await db.commit()

async def get_next_id_code(db: aiosqlite.Connection) -> str:
    async with db.execute("SELECT id_code FROM users WHERE id_code IS NOT NULL") as cursor:
        rows = await cursor.fetchall()
        max_num = 0
        prefix_len = len(ID_PREFIX)
        for row in rows:
            code = row[0]
            if code and code.startswith(ID_PREFIX):
                num_part = code[prefix_len:]
                if num_part.isdigit():
                    max_num = max(max_num, int(num_part))
        next_num = max_num + 1
        return f"{ID_PREFIX}{next_num}"

async def approve_user_atomic(user_id: int):
    """
    Thread-safe atomic approval:
    Prevents race condition, double clicking, and ID duplication.
    Returns (success: bool, message: str, id_code: str, user_dict: dict)
    """
    async with _approval_lock:
        async with get_connection() as db:
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return False, "Foydalanuvchi topilmadi", None, None
                user = dict(row)
                if user.get("status") == "approved":
                    return False, "Bu ariza allaqachon tasdiqlangan!", user.get("id_code"), user

            new_id_code = await get_next_id_code(db)
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cursor = await db.execute("""
                UPDATE users SET
                    status = 'approved',
                    id_code = ?,
                    approved_at = ?
                WHERE user_id = ? AND status != 'approved'
            """, (new_id_code, now, user_id))
            await db.commit()

            if cursor.rowcount == 0:
                return False, "Ariza allaqachon boshqa admin tomonidan tasdiqlangan!", None, None

            user["id_code"] = new_id_code
            user["status"] = "approved"
            user["approved_at"] = now
            return True, "Tasdiqlandi", new_id_code, user

async def reject_user_atomic(user_id: int):
    """
    Thread-safe atomic rejection.
    Returns (success: bool, message: str, user_dict: dict)
    """
    async with _approval_lock:
        async with get_connection() as db:
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return False, "Foydalanuvchi topilmadi", None
                user = dict(row)
                if user.get("status") == "approved":
                    return False, "Bu ariza allaqachon tasdiqlangan, rad etib bo'lmaydi!", user
                if user.get("status") == "rejected":
                    return False, "Bu ariza allaqachon rad etilgan!", user

            cursor = await db.execute("""
                UPDATE users SET status = 'rejected'
                WHERE user_id = ? AND status != 'approved'
            """, (user_id,))
            await db.commit()

            if cursor.rowcount == 0:
                return False, "Ariza allaqachon ko'rib chiqilgan!", user

            user["status"] = "rejected"
            return True, "Rad etildi", user

async def mark_as_synced(user_id: int):
    async with get_connection() as db:
        await db.execute("UPDATE users SET synced_to_sheets = 1 WHERE user_id = ?", (user_id,))
        await db.commit()

async def get_unsynced_users():
    async with get_connection() as db:
        async with db.execute("SELECT * FROM users WHERE status = 'approved' AND synced_to_sheets = 0") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_stats():
    async with get_connection() as db:
        async with db.execute("SELECT count(*) FROM users") as c:
            total = (await c.fetchone())[0]
        async with db.execute("SELECT count(*) FROM users WHERE status = 'approved'") as c:
            approved = (await c.fetchone())[0]
        async with db.execute("SELECT count(*) FROM users WHERE status = 'pending'") as c:
            pending = (await c.fetchone())[0]
        async with db.execute("SELECT count(*) FROM users WHERE status = 'rejected'") as c:
            rejected = (await c.fetchone())[0]
        return {
            "total": total,
            "approved": approved,
            "pending": pending,
            "rejected": rejected
        }

import asyncio
import database
import config
import aiosqlite

async def main():
    await database.init_db()
    
    # 1. Test next ID
    async with database.get_connection() as db:
        id1 = await database.get_next_id_code(db)
        print("Initial next ID:", id1)
        assert id1 == "YK1", f"Expected YK1, got {id1}"

    # 2. Test saving application
    test_user_id = 888888
    sample_data = {
        "username": "audit_user",
        "hudud": "🌍 Viloyat",
        "phone": "+998901234567",
        "first_name": "Ali",
        "last_name": "Valiyev",
        "passport_series": "AB1234567",
        "pinfl": "12345678901234",
        "address": "Farg'ona, Markaz",
        "passport_front_id": "photo_front_id",
        "passport_back_id": "photo_back_id"
    }
    await database.save_application(test_user_id, sample_data)
    user = await database.get_user(test_user_id)
    assert user["status"] == "pending"

    # 3. Test atomic approval
    success, msg, code, user = await database.approve_user_atomic(test_user_id)
    print("Atomic approval result:", success, msg, code)
    assert success is True
    assert code == "YK1"

    # 4. Test double approval prevention
    success2, msg2, code2, user2 = await database.approve_user_atomic(test_user_id)
    print("Double approval prevention:", success2, msg2)
    assert success2 is False

    # 5. Clean up
    async with database.get_connection() as db:
        await db.execute("DELETE FROM users WHERE user_id = ?", (test_user_id,))
        await db.commit()

    print("[AUDIT TEST] ALL DATABASE INTEGRITY TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(main())

import aiosqlite

DB_NAME = "database.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            gender TEXT,
            age INTEGER,
            weight INTEGER,
            height INTEGER,
            goal TEXT,
            activity_level TEXT DEFAULT 'moderate',
            is_premium INTEGER DEFAULT 0
        )
        """)
        
        await db.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            description TEXT,
            calories INTEGER,
            protein INTEGER,
            fat INTEGER,
            carbs INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        await db.execute("""
        CREATE TABLE IF NOT EXISTS water_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            amount_ml INTEGER,
            date DATE DEFAULT (date('now', 'localtime'))
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS workout_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            plan TEXT,
            location TEXT,
            date DATE DEFAULT (date('now', 'localtime'))
        )
        """)
        
        await db.execute("""
        CREATE TABLE IF NOT EXISTS weight_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            weight REAL,
            date DATE DEFAULT (date('now', 'localtime'))
        )
        """)

        # Добавляем activity_level если колонки ещё нет (для старых БД)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN activity_level TEXT DEFAULT 'moderate'")
        except Exception:
            pass  # Колонка уже существует

        await db.commit()
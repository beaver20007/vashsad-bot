import asyncio
import asyncpg
import os
from dotenv import load_dotenv

MIGRATIONS = [
    ('001_add_lang', '''
        ALTER TABLE users ADD COLUMN IF NOT EXISTS lang VARCHAR(5) DEFAULT 'ru';
    '''),
    ('002_add_garden_photo', '''
        ALTER TABLE users ADD COLUMN IF NOT EXISTS garden_photo_url TEXT;
    '''),
    ('003_add_last_activity', '''
        ALTER TABLE users ADD COLUMN IF NOT EXISTS last_activity TIMESTAMP DEFAULT NOW();
        CREATE INDEX IF NOT EXISTS idx_users_last_activity ON users(last_activity);
    '''),
    ('004_add_analytics_events', '''
        CREATE TABLE IF NOT EXISTS analytics_events (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT,
            event_name VARCHAR(100) NOT NULL,
            params JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_analytics_events_name ON analytics_events(event_name);
        CREATE INDEX IF NOT EXISTS idx_analytics_events_telegram ON analytics_events(telegram_id);
    '''),
    ('005_add_promo_codes', '''
        CREATE TABLE IF NOT EXISTS promo_codes (
            id SERIAL PRIMARY KEY,
            code VARCHAR(20) UNIQUE NOT NULL,
            discount INTEGER NOT NULL,
            description TEXT,
            active BOOLEAN DEFAULT TRUE,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        );
    '''),
]

async def run_migrations(dsn):
    conn = await asyncpg.connect(dsn)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            applied_at TIMESTAMP DEFAULT NOW()
        )
    """)
    applied = {r['name'] for r in await conn.fetch("SELECT name FROM schema_migrations")}
    for name, sql in MIGRATIONS:
        if name not in applied:
            await conn.execute(sql)
            await conn.execute("INSERT INTO schema_migrations(name) VALUES($1)", name)
            print(f"Applied: {name}")
        else:
            print(f"Skipped: {name} (already applied)")
    await conn.close()

if __name__ == '__main__':
    load_dotenv()
    asyncio.run(run_migrations(os.environ['DATABASE_URL']))

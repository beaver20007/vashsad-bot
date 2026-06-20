import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

PROMO_CODES = [
    ('ВЕСНА2026', 15, 'Весенняя скидка 15% на все услуги', '2026-09-01'),
    ('ПРИРОДНЫЙ10', 10, 'Скидка 10% для поклонников природного стиля', None),
    ('НИЖНИЙ20', 20, 'Скидка 20% для жителей Нижегородской области', '2026-12-31'),
    ('СТАРТ5', 5, 'Скидка 5% для новых клиентов', None),
    ('ДРУГ15', 15, 'Скидка 15% по рекомендации друга', None),
    ('ВЛАДИМИР10', 10, 'Скидка 10% для жителей Владимирской области', '2026-12-31'),
    ('СЕЗОН25', 25, 'Сезонная скидка 25% на консультации', '2026-08-31'),
]

async def seed():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            id SERIAL PRIMARY KEY, code VARCHAR(20) UNIQUE NOT NULL,
            discount INTEGER NOT NULL, description TEXT, active BOOLEAN DEFAULT TRUE,
            expires_at TIMESTAMP, created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    for code, discount, desc, expires in PROMO_CODES:
        exp = datetime.fromisoformat(expires) if expires else None
        await conn.execute(
            "INSERT INTO promo_codes(code,discount,description,expires_at) VALUES($1,$2,$3,$4) ON CONFLICT(code) DO NOTHING",
            code, discount, desc, exp
        )
        print(f"Seeded: {code} (-{discount}%)")
    await conn.close()
    print("Done!")

if __name__ == '__main__':
    load_dotenv()
    asyncio.run(seed())

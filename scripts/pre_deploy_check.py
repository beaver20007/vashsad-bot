"""
Pre-deploy checklist for ВашСад bot.
Run: python scripts/pre_deploy_check.py
Checks all required env vars, DB connectivity, and configuration.
"""
import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

REQUIRED_ENV = [
    ("TELEGRAM_BOT_TOKEN", "Telegram bot token from @BotFather"),
    ("ANTHROPIC_API_KEY", "Anthropic API key for Claude"),
    ("DATABASE_URL", "PostgreSQL connection string (Neon)"),
    ("REDIS_URL", "Redis URL (Upstash)"),
    ("DESIGNER_TELEGRAM_ID", "Designer's Telegram user ID"),
    ("DESIGNER_NAME", "Designer's name for welcome message"),
]

OPTIONAL_ENV = [
    ("YOOKASSA_SHOP_ID", "YooKassa shop ID for payments"),
    ("YOOKASSA_SECRET_KEY", "YooKassa secret key"),
    ("OPENWEATHER_API_KEY", "OpenWeatherMap API key"),
    ("ADMIN_TOKEN", "Admin token for API routes"),
    ("MINI_APP_URL", "Miniapp URL for deep links"),
    ("WELCOME_IMAGE_URL", "Welcome image URL"),
    ("DESIGNER_EMAIL", "Designer email for notifications"),
    ("NEXT_PUBLIC_VAPID_PUBLIC_KEY", "VAPID public key for push notifications"),
]

REQUIRED_FILES = [
    "bot.py",
    "config.py",
    "requirements.txt",
    "Dockerfile",
    "docker-compose.yml",
    "handlers/start.py",
    "handlers/chat.py",
    "handlers/order.py",
    "services/database.py",
    "services/scheduler.py",
]

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

def ok(msg): print(f"{GREEN}✅ {msg}{RESET}")
def fail(msg): print(f"{RED}❌ {msg}{RESET}")
def warn(msg): print(f"{YELLOW}⚠️  {msg}{RESET}")
def info(msg): print(f"{BLUE}ℹ️  {msg}{RESET}")

errors = []
warnings = []

async def check_database():
    url = os.getenv("DATABASE_URL", "")
    if not url:
        return False
    try:
        import asyncpg
        conn = await asyncpg.connect(url)
        version = await conn.fetchval("SELECT version()")
        await conn.close()
        ok(f"Database connected: {version[:40]}...")
        return True
    except Exception as e:
        fail(f"Database connection failed: {e}")
        errors.append("DATABASE_URL")
        return False

async def check_redis():
    url = os.getenv("REDIS_URL", "")
    if not url:
        return False
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(url)
        await r.ping()
        await r.aclose()
        ok("Redis connected")
        return True
    except Exception as e:
        fail(f"Redis connection failed: {e}")
        errors.append("REDIS_URL")
        return False

async def check_telegram():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return False
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.telegram.org/bot{token}/getMe") as r:
                data = await r.json()
                if data.get("ok"):
                    bot = data["result"]
                    ok(f"Bot: @{bot['username']} ({bot['first_name']})")
                    return True
                else:
                    fail(f"Bot token invalid: {data.get('description')}")
                    errors.append("TELEGRAM_BOT_TOKEN")
                    return False
    except Exception as e:
        fail(f"Telegram check failed: {e}")
        return False

async def check_anthropic():
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        return False
    if not key.startswith("sk-ant-"):
        warn("ANTHROPIC_API_KEY doesn't look like a valid Anthropic key")
        warnings.append("ANTHROPIC_API_KEY format")
        return False
    ok("Anthropic API key format valid")
    return True

async def main():
    print(f"\n{BOLD}{'='*50}{RESET}")
    print(f"{BOLD}🌿 ВашСад — Pre-Deploy Checklist{RESET}")
    print(f"{BOLD}{'='*50}{RESET}\n")

    # 1. Check required env vars
    print(f"{BOLD}📋 Required Environment Variables:{RESET}")
    for var, desc in REQUIRED_ENV:
        val = os.getenv(var, "")
        if val:
            masked = val[:6] + "..." + val[-4:] if len(val) > 12 else "***"
            ok(f"{var} = {masked}")
        else:
            fail(f"{var} — MISSING ({desc})")
            errors.append(var)

    print(f"\n{BOLD}📋 Optional Environment Variables:{RESET}")
    for var, desc in OPTIONAL_ENV:
        val = os.getenv(var, "")
        if val:
            ok(f"{var} = set")
        else:
            warn(f"{var} — not set ({desc})")
            warnings.append(var)

    # 2. Check required files
    print(f"\n{BOLD}📁 Required Files:{RESET}")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    for f in REQUIRED_FILES:
        path = os.path.join(project_root, f)
        if os.path.exists(path):
            ok(f"{f}")
        else:
            fail(f"{f} — MISSING")
            errors.append(f"file:{f}")

    # 3. Check connections
    print(f"\n{BOLD}🔌 Connections:{RESET}")
    await check_database()
    await check_redis()
    await check_telegram()
    await check_anthropic()

    # 4. Summary
    print(f"\n{BOLD}{'='*50}{RESET}")
    if errors:
        fail(f"FAILED — {len(errors)} critical issues: {', '.join(str(e) for e in errors[:5])}")
        print(f"{RED}Fix these before deploying!{RESET}")
        sys.exit(1)
    elif warnings:
        warn(f"WARNINGS — {len(warnings)} optional items missing")
        ok("All critical checks passed — safe to deploy")
    else:
        ok("ALL CHECKS PASSED — ready to deploy! 🚀")
    print()

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import sys

from sqlalchemy import text

from app.core.config import settings
from app.persistence.db import engine


async def reset_demo_data() -> None:
    if settings.app_env != "local":
        raise RuntimeError("reset-demo-data is local only")
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE run_events, messages, agent_runs, conversations CASCADE"))
        tables = (await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = current_schema() AND tablename LIKE 'checkpoint%'"))).scalars().all()
        if tables:
            quoted = ", ".join('"' + name.replace('"', '""') + '"' for name in tables)
            await conn.execute(text(f"TRUNCATE {quoted} CASCADE"))
    await engine.dispose()


if __name__ == "__main__":
    if sys.argv[1:] != ["reset-demo-data"]:
        raise SystemExit("usage: python -m app.cli reset-demo-data")
    asyncio.run(reset_demo_data())

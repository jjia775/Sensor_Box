import asyncio
from sqlalchemy import text

from app.db import engine


def _quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


async def reset_database() -> None:
    owner = engine.url.username or "postgres"
    owner_ident = _quote_ident(owner)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text(f"GRANT ALL ON SCHEMA public TO {owner_ident}"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
        await conn.execute(text("COMMENT ON SCHEMA public IS 'standard public schema'"))

    await engine.dispose()


def main() -> None:
    asyncio.run(reset_database())


if __name__ == "__main__":
    main()

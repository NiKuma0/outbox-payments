import asyncio

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine


async def database_is_reachable(engine: AsyncEngine, *, within: float = 2.0) -> bool:
    try:
        async with asyncio.timeout(within), engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError, OSError, TimeoutError:
        return False
    return True

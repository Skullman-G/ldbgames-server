from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from server.database import Game, GameBuild, Platform


# ---------- Games ----------

async def get_game(db: AsyncSession, game_id: str) -> Optional[Game]:
    result = await db.execute(
        select(Game).where(Game.id == game_id)
    )
    return result.scalar_one_or_none()


async def list_games(db: AsyncSession) -> list[Game]:
    result = await db.execute(select(Game))
    return result.scalars().all()


# ---------- Builds ----------

async def list_game_builds(db: AsyncSession, game_id: str) -> list[GameBuild]:
    result = await db.execute(
        select(GameBuild).where(GameBuild.game_id == game_id)
    )
    return result.scalars().all()


async def get_game_build(
    db: AsyncSession,
    game_id: str,
    version: str,
    platform_id: int,
) -> Optional[GameBuild]:
    result = await db.execute(
        select(GameBuild).where(
            GameBuild.game_id == game_id,
            GameBuild.version == version,
            GameBuild.platform_id == platform_id,
        )
    )
    return result.scalar_one_or_none()


async def delete_game_build(
    db: AsyncSession,
    game_id: str,
    version: str,
    platform_id: int,
) -> Optional[str]:
    """
    Deletes build and returns archive_path if deleted.
    """
    build = await get_game_build(db, game_id, version, platform_id)
    if not build:
        return None

    archive_path = build.archive_path
    await db.delete(build)
    await db.commit()
    return archive_path


# ---------- Platforms ----------

async def get_platform(db: AsyncSession, platform_id: int) -> Optional[Platform]:
    result = await db.execute(
        select(Platform).where(Platform.id == platform_id)
    )
    return result.scalar_one_or_none()

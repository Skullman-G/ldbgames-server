from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Platform(Base):
    __tablename__ = "platform"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]

class GameBuild(Base):
    __tablename__ = "game_builds"

    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), primary_key=True)
    version: Mapped[str] = mapped_column(primary_key=True)
    archive_path: Mapped[str]
    binary_path: Mapped[str]
    platform_id: Mapped[int] = mapped_column(ForeignKey("platform.id"), primary_key=True)


class Game(Base):
    __tablename__ = "games"
    
    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    grid: Mapped[str]
    header: Mapped[str]
    hero: Mapped[str]
    icon: Mapped[str]
    logo: Mapped[str]
    description: Mapped[str]
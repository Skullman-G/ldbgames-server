from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class GameBuild(Base):
    __tablename__ = "game_builds"

    gameid: Mapped[str] = mapped_column(ForeignKey("games.id"), primary_key=True)
    version: Mapped[str] = mapped_column(primary_key=True)
    binary_path: Mapped[str]

class Game(Base):
    __tablename__ = "games"
    
    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    grid: Mapped[str]
    header: Mapped[str]
    hero: Mapped[str]
    icon: Mapped[str]
    logo: Mapped[str]
from fastapi import FastAPI, HTTPException, Depends
from fastapi import UploadFile, File, Form
from pathlib import Path
import json
import uvicorn
import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from server.database import Base, Game, GameBuild
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

class GameBuildResponse(BaseModel):
    version: str
    archive_path: str

class GameResponse(BaseModel):
    id: str
    name: str
    grid: str
    header: str
    hero: str
    icon: str
    logo: str
    builds: list[GameBuildResponse]

class AddGameRequest(BaseModel):
    id: str
    name: str

class UpdateGameRequest(BaseModel):
    name: str
    grid: str
    header: str
    hero: str
    icon: str
    logo: str


BASE_DIR = Path(os.environ.get("LDBGAMES_DATADIR", Path(__file__).parent))
DATABASE_URL = f"sqlite+aiosqlite:///{BASE_DIR}/data/games.db"
STATIC_DIR = BASE_DIR / "static"
IMAGE_DIR = STATIC_DIR / "img"

ALLOWED_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
VALID_IMAGE_FIELDS = ["grid", "header", "hero", "icon", "logo"]

ALLOWED_ARCHIVE_EXTENSION = ".tar.gz"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)

app = FastAPI(title="LDBGames API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/img",
    StaticFiles(directory=IMAGE_DIR),
    name="img"
)

async def get_db():
    async with async_session() as session:
        yield session

def validate_archive(filename: str):
    if not filename.endswith(ALLOWED_ARCHIVE_EXTENSION):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported archive type. Allowed: {', '.join(ALLOWED_ARCHIVE_EXTENSION)}"
        )
    return ALLOWED_ARCHIVE_EXTENSION

def get_img_static_path(game_id: str, image_type: str, img_name: str):
    img_path = STATIC_DIR / "img" / game_id / image_type / img_name
    if not img_path.exists() or img_path.is_dir():
        return ""
    
    static_img_path = f"/img/{game_id}/{image_type}/{img_name}"
    return static_img_path

async def get_game_builds(db: AsyncSession, game_id: str) -> list[GameBuild]:
    result = await db.execute(select(GameBuild).where(GameBuild.game_id == game_id))
    return result.scalars().all()

async def mk_game_response(game: Game, db: AsyncSession) -> GameResponse:
    builds = await get_game_builds(db, game.id)
    return GameResponse(
        id=game.id,
        name=game.name,
        grid=get_img_static_path(game.id, "grid", game.grid),
        header=get_img_static_path(game.id, "header", game.header),
        hero=get_img_static_path(game.id, "hero", game.hero),
        icon=get_img_static_path(game.id, "icon", game.icon),
        logo=get_img_static_path(game.id, "logo", game.logo),
        builds=[
            GameBuildResponse(
                version=b.version,
                archive_path=b.archive_path,
            ) for b in builds
        ],
    )

async def get_game(db: AsyncSession, game_id: str) -> Optional[Game]:
    result = await db.execute(select(Game).where(Game.id == game_id))
    return result.scalar_one_or_none()

@app.get("/api/games", response_model=list[GameResponse])
async def list_games(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Game))
    games = result.scalars().all()
    return [
        await mk_game_response(g, db) for g in games
    ]

@app.get("/api/games/{game_id}", response_model=GameResponse)
async def game_metadata(game_id: str, db: AsyncSession = Depends(get_db)):
    game = await get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return await mk_game_response(game, db)

@app.post("/api/games/{game_id}/build/add", response_model=GameResponse)
async def add_game_build(
    game_id: str,
    version: str = Form(...),
    binary_path: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    game = await get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    suffix = validate_archive(file.filename)

    builds_dir = STATIC_DIR / "builds" / game_id
    builds_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"{game_id}_{version}"
    archive_base = builds_dir / base_name

    content = await file.read()
    with create_unique_file(archive_base, suffix, "b") as buffer:
        buffer.write(content)
        archive_path = buffer.name

    build = GameBuild(
        game_id=game_id,
        version=version,
        binary_path=binary_path,
        archive_path=str(archive_path),
    )
    db.add(build)
    await db.commit()

    return await mk_game_response(game, db)

@app.get("/api/games/{game_id}/img/{image_type}/list")
async def game_img_all(game_id: str, image_type: str, limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    if image_type not in VALID_IMAGE_FIELDS:
        raise HTTPException(status_code=400, detail=f"Invalid image type: {image_type}, Must be one of: {', '.join(VALID_IMAGE_FIELDS)}")
    
    game = await get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    img_type_dir = IMAGE_DIR / game_id / image_type
    img_type_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(img_type_dir.iterdir())
    images = [
        f"/img/{game_id}/{image_type}/{f.name}" for f in files
        if f.name.lower().endswith(ALLOWED_IMAGE_EXTENSIONS)
    ]
    return images[offset: offset + limit]

@app.post("/api/games/add", response_model=GameResponse)
async def add_game(game: AddGameRequest, db: AsyncSession = Depends(get_db)):
    existing = await get_game(db, game.id)
    if existing:
        raise HTTPException(status_code=400, detail="Game with this id already exists")
    
    new_game = Game(
        id=game.id,
        name=game.name,
        grid='',
        header='',
        hero='',
        icon='',
        logo='',
    )
    db.add(new_game)
    await db.commit()
    await db.refresh(new_game)
    
    return await mk_game_response(new_game, db)

@app.post("/api/games/{game_id}/delete", status_code=204)
async def delete_game(game_id: str, db: AsyncSession = Depends(get_db)):
    game = await get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    await db.delete(game)
    await db.commit()

@app.post("/api/games/{game_id}/update", response_model=GameResponse)
async def update_game(game_id: str, game: UpdateGameRequest, db: AsyncSession = Depends(get_db)):
    existing = await get_game(db, game_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Game not found")

    existing.name = game.name
    existing.grid = game.grid
    existing.header = game.header
    existing.hero = game.hero
    existing.icon = game.icon
    existing.logo = game.logo

    db.add(existing)
    await db.commit()
    await db.refresh(existing)

    return await mk_game_response(existing, db)

def create_unique_file(base_name, suffix, write_mode="b"):
    i = 0
    while True:
        name = f"{base_name}{'' if i == 0 else f'_{i}'}{suffix}"
        path = Path(name)
        try:
            return path.open(f"x{write_mode}")
        except FileExistsError:
            i += 1

@app.post("/api/games/{game_id}/img/{image_type}/upload")
async def game_img_upload(game_id: str, image_type: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    if image_type not in VALID_IMAGE_FIELDS:
        raise HTTPException(status_code=400, detail=f"Invalid image type: {image_type}, Must be one of: {', '.join(VALID_IMAGE_FIELDS)}")
    
    game = await get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}")
    
    img_folder = STATIC_DIR / "img" / game_id / image_type
    img_folder.mkdir(parents=True, exist_ok=True)

    img_path = img_folder / image_type

    content = await file.read()
    with create_unique_file(img_path, suffix, "b") as buffer:
        buffer.write(content)
        filename = buffer.name

    return {"message": f"{image_type} image uploaded successfully", "filename": filename}

@app.on_event("startup")
async def startup_event():
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Check if we need to migrate from JSON file
    data_file = BASE_DIR / "data" / "games.json"
    if data_file.exists():
        print("Migrating data from JSON file to database...")
        async with async_session() as session:
            # Check if database is already populated
            result = await session.execute(select(Game))
            existing_games = result.scalars().all()
            if not existing_games:
                # Load and migrate data
                with open(data_file, "r") as f:
                    games_data = json.load(f)
                
                for game_data in games_data:
                    game = Game(
                        id=game_data["id"],
                        name=game_data["name"],
                        grid=game_data.get("img", {}).get("grid", ""),
                        header=game_data.get("img", {}).get("header", ""),
                        hero=game_data.get("img", {}).get("hero", ""),
                        icon=game_data.get("img", {}).get("icon", ""),
                        logo=game_data.get("img", {}).get("logo", "")
                    )
                    session.add(game)
                await session.commit()
                print(f"Migrated {len(games_data)} games to database")
            else:
                print("Database already contains data, skipping migration")

def main():
    uvicorn.run(app, host="0.0.0.0", port=8000)

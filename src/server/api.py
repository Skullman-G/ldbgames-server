from fastapi import FastAPI, HTTPException, Depends
from fastapi import UploadFile, File, Form
from pathlib import Path
import json
import uvicorn
import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
from pydantic import BaseModel
from server.database import Base, Game, GameBuild, Platform
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import server.crud as crud

class PlatformResponse(BaseModel):
    id: int
    name: str
    used: bool

class GameBuildResponse(BaseModel):
    version: str
    archive_path: str
    platform: PlatformResponse

class GameResponse(BaseModel):
    id: str
    name: str
    grid: str
    header: str
    hero: str
    icon: str
    logo: str
    builds: list[GameBuildResponse]
    description: str

BASE_DIR = Path(os.environ.get("LDBGAMES_DATADIR", Path(__file__).parent))
DATABASE_URL = f"sqlite+aiosqlite:///{BASE_DIR}/data/games.db"
STATIC_DIR = BASE_DIR / "static"
IMAGE_DIR = STATIC_DIR / "img"
BUILDS_DIR = STATIC_DIR / "builds"

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
app.mount(
    "/builds",
    StaticFiles(directory=BUILDS_DIR),
    name="builds"
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

def get_img_static_path(image_path: str):
    full_path = STATIC_DIR / image_path.lstrip('/')
    if not full_path.exists() or full_path.is_dir():
        return ""
    
    return image_path

async def mk_game_response(db: AsyncSession, game: Game) -> GameResponse:
    builds = await crud.list_game_builds(db, game.id)

    build_responses = []
    for b in builds:
        platform = await crud.get_platform(db, b.platform_id)
        build_responses.append(
            GameBuildResponse(
                version=b.version,
                archive_path=b.archive_path,
                platform=PlatformResponse(
                    id=platform.id,
                    name=platform.name,
                    used=True,
                ),
            )
        )

    return GameResponse(
        id=game.id,
        name=game.name,
        grid=get_img_static_path(game.grid),
        header=get_img_static_path(game.header),
        hero=get_img_static_path(game.hero),
        icon=get_img_static_path(game.icon),
        logo=get_img_static_path(game.logo),
        builds=build_responses,
        description=game.description or "",
    )

@app.get("/api/platforms", response_model=list[PlatformResponse])
async def list_platforms(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Platform))
    platforms = result.scalars().all()
    return [
        PlatformResponse(
            id=p.id,
            name=p.name,
            used=await crud.platform_has_builds(db, p.id),
        ) for p in platforms
    ]

@app.get("/api/games", response_model=list[GameResponse])
async def list_games_endpoint(db: AsyncSession = Depends(get_db)):
    games = await crud.list_games(db)
    return [await mk_game_response(db, g) for g in games]

@app.get("/api/games/{game_id}", response_model=GameResponse)
async def game_metadata(game_id: str, db: AsyncSession = Depends(get_db)):
    game = await crud.get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return await mk_game_response(db, game)

@app.post("/api/games/{game_id}/build/add", response_model=GameResponse)
async def add_game_build(
    game_id: str,
    version: str = Form(...),
    binary_path: str = Form(...),
    platform_id: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    game = await crud.get_game(db, game_id)
    if not game:
        raise HTTPException(
            status_code=404,
            detail=f"Game with id '{game_id} not found"
        )

    existing_build = await crud.get_game_build(db, game_id, version, platform_id)
    if existing_build:
        raise HTTPException(
            status_code=400,
            detail=f"Build version '{version}' already exists for this game"
        )
    
    platform = await crud.get_platform(db, platform_id)
    if not platform:
        raise HTTPException(
            status_code=400,
            detail="Platform does not exist"
        )

    suffix = validate_archive(file.filename)

    builds_dir = BUILDS_DIR / game_id
    builds_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"{game_id}_{platform.name}_{version}"
    archive_base = builds_dir / base_name

    content = await file.read()
    with create_unique_file(archive_base, suffix, "b") as buffer:
        buffer.write(content)
        archive_path = buffer.name

    public_archive_path = f"/builds/{game_id}/{Path(archive_path).name}"

    build = GameBuild(
        game_id=game_id,
        version=version,
        binary_path=binary_path,
        archive_path=public_archive_path,
        platform_id=platform_id,
    )
    db.add(build)
    await db.commit()

    return await mk_game_response(db, game)

@app.post("/api/games/{game_id}/build/delete", response_model=GameResponse)
async def delete_game_build_endpoint(
    game_id: str,
    version: str = Form(...),
    platform_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    archive_path = await crud.delete_game_build(
        db, game_id, version, platform_id
    )

    if not archive_path:
        raise HTTPException(status_code=404, detail="Build not found")

    fs_path = STATIC_DIR / archive_path.lstrip("/")
    fs_path.unlink(missing_ok=True)

    game = await crud.get_game(db, game_id)
    return await mk_game_response(db, game)


@app.get("/api/games/{game_id}/img/{image_type}/list")
async def game_img_all(game_id: str, image_type: str, limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    if image_type not in VALID_IMAGE_FIELDS:
        raise HTTPException(status_code=400, detail=f"Invalid image type: {image_type}, Must be one of: {', '.join(VALID_IMAGE_FIELDS)}")
    
    game = await crud.get_game(db, game_id)
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

@app.post("/api/games/{game_id}/img/delete")
async def game_delete_img(game_id: str, image_path: str = Form(...), db: AsyncSession = Depends(get_db)):
    game = crud.get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    fs_path = STATIC_DIR / image_path.lstrip("/")
    if not fs_path.exists() or fs_path.is_dir():
        raise HTTPException(status_code=400, detail="Invalid image path")
    
    fs_path.unlink()

@app.post("/api/games/add", response_model=GameResponse)
async def add_game(
    game_id: str = Form(...),
    game_name: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    existing = await crud.get_game(db, game_id)
    if existing:
        raise HTTPException(status_code=400, detail="Game with this id already exists")
    
    new_game = Game(
        id=game_id,
        name=game_name,
        grid='',
        header='',
        hero='',
        icon='',
        logo='',
    )
    db.add(new_game)
    await db.commit()
    await db.refresh(new_game)
    
    return await mk_game_response(db, new_game)

@app.post("/api/games/{game_id}/delete", status_code=204)
async def delete_game(game_id: str, db: AsyncSession = Depends(get_db)):
    game = await crud.get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    await db.delete(game)
    await db.commit()

@app.post("/api/games/{game_id}/update", response_model=GameResponse)
async def update_game_metadata(
    game_id: str,
    game_name: str = Form(...),
    grid_path: str = Form(...),
    header_path: str = Form(...),
    hero_path: str = Form(...),
    icon_path: str = Form(...),
    logo_path: str = Form(...),
    game_description: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    existing = await crud.get_game(db, game_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Game not found")

    existing.name = game_name
    existing.grid = grid_path
    existing.header = header_path
    existing.hero = hero_path
    existing.icon = icon_path
    existing.logo = logo_path
    existing.description = game_description

    db.add(existing)
    await db.commit()
    await db.refresh(existing)

    return await mk_game_response(db, existing)

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
    
    game = await crud.get_game(db, game_id)
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

@app.post("/api/platforms/add")
async def platform_add(platform_name: str = Form(...), db: AsyncSession = Depends(get_db)):
    if not platform_name:
        raise HTTPException(status_code=400, detail="Invalid platform name")
    
    existing_platform = await crud.get_platform_by_name(db, platform_name)
    if existing_platform:
        raise HTTPException(status_code=400, detail=f"Platform with the name {platform_name} already exists")
    
    new_platform = Platform(
        name=platform_name,
    )
    
    db.add(new_platform)

    await db.commit()
    await db.refresh(new_platform)

@app.post("/api/platforms/{platform_id}/delete")
async def platform_delete(platform_id: str, db: AsyncSession = Depends(get_db)):
    existing_platform = await crud.get_platform(db, platform_id)
    if not existing_platform:
        raise HTTPException(status_code=404, detail=f"Platform with id {platform_id} does not exist")
    
    in_use = await crud.platform_has_builds(db, platform_id)
    
    if in_use:
        raise HTTPException(status_code=400, detail=f"Platform with id {platform_id} is still in use and cannot be removed")
    
    await db.delete(existing_platform)
    await db.commit()

@app.post("/api/platforms/{platform_id}/update")
async def platform_update(platform_id: str, platform_name: str = Form(...), db: AsyncSession = Depends(get_db)):
    if not platform_name:
        raise HTTPException(status_code=400, detail="Invalid platform name")
    
    platform = await crud.get_platform(db, platform_id)
    if not platform:
        raise HTTPException(status_code=400, detail=f"Platform with the name {platform_name} does not exist")
    
    platform.name = platform_name
    
    db.add(platform)

    await db.commit()
    await db.refresh(platform)

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

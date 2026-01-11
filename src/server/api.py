from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import json
import uvicorn
import os

BASE_DIR = Path(os.environ.get("LDBGAMES_DATADIR", Path(__file__).parent))
DATA_FILE = Path(BASE_DIR / "data/games.json")
STATIC_DIR = Path(BASE_DIR / "static")

with open(DATA_FILE, "r") as f:
    games_data = json.load(f)

app = FastAPI(title="LDBGames API")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_game(game_id: str):
    for game in games_data:
        if game["id"] == game_id:
            return game
    return None

@app.get("/api/games")
def list_games():
    return [
        {
            "id": g["id"],
            "name": g["name"],
            "version": g["version"],
            "url": g["url"],
            "binary": g["binary"],
            "img": g.get("img", None)
        } for g in games_data
    ]

@app.get("/api/games/{game_id}")
def game_metadata(game_id: str):
    game = get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return game

@app.get("/api/games/{game_id}/download")
def game_download(game_id: str):
    game = get_game(game_id)
    return FileResponse(
        path= STATIC_DIR / game["url"],
        filename=f"{game["id"]}-{game["version"]}.tar.gz",
        media_type="application/gzip"
    )

@app.get("/api/games/{game_id}/img/{img_id}")
def game_img(game_id: str, img_id: str):
    game = get_game(game_id)
    img = game.get("img", None)
    if not img:
        raise HTTPException(status_code=404, detail="This game has no images")
    
    img_name = img.get(img_id, None)
    if not img_name:
        raise HTTPException(status_code=404, detail=f"Specified Image not found: {img_id}")
    
    img_path = STATIC_DIR / "img" / game_id / img_name
    if not img_path.exists():
        raise HTTPException(status_code=404, detail=f"Image file not found on server: {img_id}")
    
    return FileResponse(path = img_path, filename=img_name, media_type=f"image/{img_path.suffix}")

def main():
    uvicorn.run(app, host="0.0.0.0", port=8000)

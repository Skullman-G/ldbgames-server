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
            "sha256": g["sha256"],
            "img": g.get("img", None),
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

def main():
    uvicorn.run(app, host="0.0.0.0", port=8000)

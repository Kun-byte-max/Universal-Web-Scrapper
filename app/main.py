from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

from app.config import settings, BASE_DIR
from app.api.routes import router as api_router

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="Universal Website-to-JSON Scraper API"
)

# Static & Templates setup
static_dir = BASE_DIR / "static"
templates_dir = BASE_DIR / "templates"

static_dir.mkdir(exist_ok=True)
templates_dir.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(api_router, prefix="/api")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    return FileResponse(templates_dir / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)

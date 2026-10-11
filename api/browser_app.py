"""Production local-browser entrypoint; never serves the workspace as static files."""

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

from .main import app


DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


def frontend_file(url_path: str, dist: Path = DIST) -> Path:
    """Resolve a static asset or SPA page without intercepting missing API routes."""
    if url_path.split("/", 1)[0] in {"api", "docs", "redoc", "openapi.json"}:
        raise HTTPException(404, "Not found")
    root = dist.resolve()
    candidate = (root / url_path).resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(404, "Not found")
    if candidate.is_file():
        return candidate
    if Path(url_path).suffix or url_path.startswith("assets/"):
        raise HTTPException(404, "Not found")
    index = root / "index.html"
    if not index.is_file():
        raise HTTPException(503, "Browser assets are missing. Reinstall the distribution.")
    return index


@app.get("/{url_path:path}", include_in_schema=False)
def browser_page(url_path: str):
    if url_path == 'favicon.ico' and not (DIST / 'favicon.ico').is_file():
        return Response(status_code=204)
    return FileResponse(frontend_file(url_path))

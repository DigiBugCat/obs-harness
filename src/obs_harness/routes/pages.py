"""Page routes serving HTML files.

Serves dashboard, channel browser sources, and auth-related pages.
"""

from html import escape
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from ..auth import require_auth_redirect
from . import get_state, require_santa_feature
from ..state import AppState

router = APIRouter(tags=["Pages"])


def get_static_dir(request: Request) -> Path:
    """Get static directory path from app state."""
    return request.app.state.static_dir


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    static_dir: Path = Depends(get_static_dir),
    tenant_id: str = Depends(require_auth_redirect),
):
    """Serve the dashboard page."""
    dashboard_path = static_dir / "dashboard.html"
    if dashboard_path.exists():
        return FileResponse(dashboard_path)
    return HTMLResponse("<html><body><h1>OBS Harness Dashboard</h1><p>Dashboard not found.</p></body></html>")


@router.get("/channel/{name}", response_class=HTMLResponse)
async def channel_page(name: str, static_dir: Path = Depends(get_static_dir)):
    """Serve the browser source page for a channel."""
    channel_path = static_dir / "channel.html"
    if channel_path.exists():
        return FileResponse(channel_path)
    return HTMLResponse(f"<html><body><h1>Channel: {escape(name)}</h1><p>Channel template not found.</p></body></html>")


@router.get("/editor", response_class=HTMLResponse)
async def editor_page(
    static_dir: Path = Depends(get_static_dir),
    tenant_id: str = Depends(require_auth_redirect),
):
    """Serve the text animation editor page."""
    editor_path = static_dir / "editor.html"
    if editor_path.exists():
        return FileResponse(editor_path)
    return HTMLResponse("<html><body><h1>Text Editor</h1><p>Editor not found.</p></body></html>")


@router.get("/login", response_class=HTMLResponse)
async def login_page(static_dir: Path = Depends(get_static_dir)):
    """Serve the login page."""
    login_path = static_dir / "login.html"
    if login_path.exists():
        return FileResponse(login_path)
    return HTMLResponse("<html><body><h1>Login</h1><a href='/auth/twitch'>Login with Twitch</a></body></html>")


@router.get("/logout")
async def logout():
    """Clear session and redirect to login."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("tenant_id")
    return response


@router.get("/twitch", response_class=HTMLResponse)
async def twitch_page(
    static_dir: Path = Depends(get_static_dir),
    tenant_id: str = Depends(require_auth_redirect),
):
    """Serve the Twitch OAuth sign-in page."""
    twitch_path = static_dir / "twitch.html"
    if twitch_path.exists():
        return FileResponse(twitch_path)
    return HTMLResponse("<html><body><h1>Twitch</h1><p>Twitch page not found.</p></body></html>")


@router.get("/santa", response_class=HTMLResponse)
async def santa_page(
    static_dir: Path = Depends(get_static_dir),
    tenant_id: str = Depends(require_auth_redirect),
    _santa: None = Depends(require_santa_feature),
):
    """Serve the Santa Timmy dashboard page."""
    santa_path = static_dir / "santa.html"
    if santa_path.exists():
        return FileResponse(santa_path)
    return HTMLResponse("<html><body><h1>Santa Timmy</h1><p>Santa dashboard not found.</p></body></html>")

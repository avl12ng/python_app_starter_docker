"""Création de l'application FastAPI. Lancement : uvicorn --factory app.main:create_app"""

from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import quote

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.account.routes import router as account_router
from app.admin.routes import router as admin_router
from app.auth.deps import LoginRequired, PermissionDenied, require_user
from app.auth.routes import router as auth_router
from app.auth.setup import router as setup_router
from app.config import Settings, get_settings
from app.core import permissions as perms
from app.core.security import CSRFError, SecurityHeadersMiddleware, csrf_protect, safe_next
from app.core.sessions import ServerSessionMiddleware
from app.db import get_db, init_engine
from app.engine.routes import router as engine_router
from app.models import User
from app.web import BASE_DIR, configure, flash, redirect, render


def _wants_json(request: Request) -> bool:
    return request.url.path.startswith("/api/") or "application/json" in request.headers.get("accept", "")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)
    init_engine(settings.database_url)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        dependencies=[Depends(csrf_protect)],
        docs_url="/api/docs" if settings.debug else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.debug else None,
    )
    app.state.settings = settings
    configure(settings)
    app.dependency_overrides[get_settings] = lambda: settings

    # Ordre : le dernier ajouté s'exécute en premier (en-têtes de sécurité autour de tout le reste).
    app.add_middleware(
        ServerSessionMiddleware,
        cookie_name=settings.session_cookie,
        idle_minutes=settings.session_idle_minutes,
        cookie_secure=settings.cookie_secure,
    )
    app.add_middleware(SecurityHeadersMiddleware)

    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    app.include_router(setup_router)
    app.include_router(auth_router)
    app.include_router(account_router)
    app.include_router(admin_router)
    app.include_router(engine_router)

    @app.get("/")
    def home(request: Request, user: User = Depends(require_user)):
        tiles = [item for item in _home_tiles() if item["permission"] is None or user.can(item["permission"])]
        prev = request.state.session.get("prev_login")
        prev_login = datetime.fromisoformat(prev) if prev else None
        return render(request, "home.html", active="home", tiles=tiles, prev_login=prev_login)

    @app.get("/health", include_in_schema=False)
    def health(db: Session = Depends(get_db)):
        db.execute(text("SELECT 1"))
        return {"status": "ok"}

    # ------------------------------------------------------------------ erreurs

    @app.exception_handler(LoginRequired)
    async def _login_required(request: Request, _exc):
        if _wants_json(request):
            return JSONResponse({"error": "authentication_required"}, status_code=401)
        target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return redirect(f"/login?next={quote(target)}" if target != "/" else "/login")

    @app.exception_handler(PermissionDenied)
    async def _forbidden(request: Request, _exc):
        if _wants_json(request):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        return render(
            request,
            "errors/error.html",
            status_code=403,
            code=403,
            message="Vous n'avez pas les droits nécessaires pour accéder à cette page.",
        )

    @app.exception_handler(CSRFError)
    async def _csrf(request: Request, _exc):
        if _wants_json(request):
            return JSONResponse({"error": "csrf"}, status_code=403)
        flash(request, "error", "La page a expiré. Merci de recommencer.")
        referer = request.headers.get("referer", "")
        path = "/" + referer.split("/", 3)[3] if referer.count("/") >= 3 else "/login"
        return redirect(safe_next(path, "/login"))

    @app.exception_handler(RequestValidationError)
    async def _invalid(request: Request, exc):
        if _wants_json(request):
            return JSONResponse({"error": "invalid_request", "detail": exc.errors()}, status_code=422)
        return render(
            request, "errors/error.html", status_code=400, code=400, message="La demande est incomplète ou invalide."
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        if _wants_json(request):
            return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
        message = "Cette page n'existe pas." if exc.status_code == 404 else "Une erreur est survenue."
        return render(request, "errors/error.html", status_code=exc.status_code, code=exc.status_code, message=message)

    return app


def _home_tiles() -> list[dict]:
    return [
        {
            "title": "Moteur",
            "text": "Lancer un calcul avec le moteur Python.",
            "href": "/engine",
            "icon": "science",
            "permission": perms.ENGINE_RUN,
        },
        {
            "title": "Mon compte",
            "text": "Courriel, mot de passe et double authentification.",
            "href": "/account",
            "icon": "user",
            "permission": None,
        },
        {
            "title": "Utilisateurs",
            "text": "Créer, modifier ou désactiver des comptes.",
            "href": "/admin/users",
            "icon": "group",
            "permission": perms.USERS_MANAGE,
        },
        {
            "title": "Journal d'audit",
            "text": "Connexions et actions sensibles des 12 derniers mois.",
            "href": "/admin/audit",
            "icon": "history",
            "permission": perms.AUDIT_VIEW,
        },
    ]

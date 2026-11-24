"""Branchement web du moteur : page /engine et API JSON /api/engine/run (protégées par permission)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import require_permission
from app.config import Settings, get_settings
from app.core import audit
from app.core import permissions as perms
from app.core.security import client_ip
from app.db import get_db
from app.engine.core import EngineError, EngineInput, parse_values, run
from app.models import User
from app.web import render

router = APIRouter()


@router.get("/engine")
def engine_page(request: Request, user: User = Depends(require_permission(perms.ENGINE_RUN))):
    return render(request, "engine/engine.html", active="engine", result=None, form={})


@router.post("/engine")
def engine_submit(
    request: Request,
    label: str = Form(""),
    values: str = Form(""),
    user: User = Depends(require_permission(perms.ENGINE_RUN)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    form = {"label": label, "values": values}
    try:
        result = run(EngineInput(values=parse_values(values), label=label))
    except EngineError as exc:
        return render(
            request, "engine/engine.html", status_code=400, active="engine", result=None, form=form, error=str(exc)
        )
    audit.record(
        db,
        "engine.run",
        actor=user,
        target_type="engine",
        details={"label": result.label, "valeurs": result.count},
        ip=client_ip(request),
        retention_days=settings.audit_retention_days,
    )
    db.commit()
    return render(request, "engine/engine.html", active="engine", result=result, form=form)


class EngineRequest(BaseModel):
    values: list[float] = Field(min_length=1)
    label: str = ""


@router.post("/api/engine/run")
def engine_api(payload: EngineRequest, user: User = Depends(require_permission(perms.ENGINE_RUN))):
    """API JSON utilisable depuis le JavaScript de l'application (en-tête X-CSRF-Token obligatoire)."""
    try:
        return {"ok": True, "result": run(EngineInput(values=payload.values, label=payload.label)).as_dict()}
    except EngineError as exc:
        return {"ok": False, "error": str(exc)}

import base64
import os
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.auth import get_current_user, get_effective_empresa_id, require_admin

router = APIRouter()

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/svg+xml"}
MAX_SIZE      = 2 * 1024 * 1024  # 2 MB


# ── GET datos empresa ─────────────────────────────────────────────────────────

@router.get("/")
def obtener(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    eid  = get_effective_empresa_id(user, request)
    e    = db.query(models.Empresa).filter(models.Empresa.id == eid).first()
    if not e:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return {
        "id":                e.id,
        "nombre":            e.nombre,
        "email":             e.email       or "",
        "telefono":          e.telefono    or "",
        "direccion":         e.direccion   or "",
        "nif":               e.nif         or "",
        "logo":              e.logo or None,   # data URI completo
        "color_corporativo": e.color_corporativo or "#1E40AF",
    }


# ── PUT datos empresa ─────────────────────────────────────────────────────────

@router.put("/")
def actualizar(data: dict, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    eid   = get_effective_empresa_id(admin, request)
    e     = db.query(models.Empresa).filter(models.Empresa.id == eid).first()
    if not e:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    for campo in ("nombre", "email", "telefono", "direccion", "nif"):
        if campo in data and data[campo] is not None:
            setattr(e, campo, str(data[campo]).strip())

    if "color_corporativo" in data:
        color = str(data["color_corporativo"]).strip()
        if not color.startswith("#") or len(color) not in (4, 7):
            raise HTTPException(status_code=400, detail="Color no válido. Usa formato hexadecimal (#RRGGBB)")
        e.color_corporativo = color

    db.commit()
    return {"ok": True}


# ── POST logo ─────────────────────────────────────────────────────────────────

@router.post("/logo")
async def subir_logo(request: Request, logo: UploadFile = File(...), db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    eid   = get_effective_empresa_id(admin, request)
    e     = db.query(models.Empresa).filter(models.Empresa.id == eid).first()
    if not e:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    if logo.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Formato no permitido. Usa JPG, PNG, WebP o SVG.")

    contenido = await logo.read()
    if len(contenido) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="El logo no puede superar 2 MB.")

    # Guardar como data URI en la base de datos (persiste en PostgreSQL)
    b64 = base64.b64encode(contenido).decode("utf-8")
    data_uri = f"data:{logo.content_type};base64,{b64}"

    e.logo = data_uri
    db.commit()
    return {"ok": True, "logo": data_uri}


# ── DELETE logo ───────────────────────────────────────────────────────────────

@router.delete("/logo")
def eliminar_logo(request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    eid   = get_effective_empresa_id(admin, request)
    e     = db.query(models.Empresa).filter(models.Empresa.id == eid).first()
    if not e:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    e.logo = None
    db.commit()
    return {"ok": True}

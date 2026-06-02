from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_admin, hash_password

router = APIRouter()


@router.get("/", response_model=List[schemas.UsuarioResponse])
def listar_usuarios(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    return db.query(models.Usuario).filter(
        models.Usuario.empresa_id == user.empresa_id
    ).order_by(models.Usuario.nombre).all()


@router.post("/", response_model=schemas.UsuarioResponse)
def crear_usuario(data: schemas.UsuarioCreate, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    if db.query(models.Usuario).filter(models.Usuario.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email ya registrado")
    nuevo = models.Usuario(
        empresa_id=admin.empresa_id,
        nombre=data.nombre,
        email=data.email,
        password_hash=hash_password(data.password),
        rol=data.rol
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.put("/{id}/activar")
def toggle_usuario(id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    u = db.query(models.Usuario).filter(
        models.Usuario.id == id,
        models.Usuario.empresa_id == admin.empresa_id
    ).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if u.id == admin.id:
        raise HTTPException(status_code=400, detail="No puedes desactivarte a ti mismo")
    u.activo = not u.activo
    db.commit()
    return {"ok": True, "activo": u.activo}


@router.put("/{id}/password")
def cambiar_password(id: int, body: dict, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    u = db.query(models.Usuario).filter(
        models.Usuario.id == id,
        models.Usuario.empresa_id == admin.empresa_id
    ).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    nueva = body.get("password", "")
    if len(nueva) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres")
    u.password_hash = hash_password(nueva)
    db.commit()
    return {"ok": True}

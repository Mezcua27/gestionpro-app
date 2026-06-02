import os
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.auth import require_superadmin, hash_password

router = APIRouter()

SISTEMA_EMAIL = "soporte@gestionpro.sistema"


def _cookie_opts():
    secure = not os.getenv("DATABASE_URL", "sqlite").startswith("sqlite")
    return dict(httponly=True, samesite="lax", secure=secure)


# ── Listar empresas ───────────────────────────────────────────────────────────

@router.get("/empresas")
def listar_empresas(request: Request, db: Session = Depends(get_db)):
    require_superadmin(request, db)
    empresas = db.query(models.Empresa).filter(
        models.Empresa.email != SISTEMA_EMAIL
    ).order_by(models.Empresa.created_at.desc()).all()
    resultado = []
    for e in empresas:
        resultado.append({
            "id": e.id,
            "nombre": e.nombre,
            "email": e.email,
            "telefono": e.telefono or "",
            "nif": e.nif or "",
            "direccion": e.direccion or "",
            "created_at": e.created_at.strftime("%d/%m/%Y") if e.created_at else "",
            "usuarios":      db.query(models.Usuario).filter(models.Usuario.empresa_id == e.id).count(),
            "clientes":      db.query(models.Cliente).filter(models.Cliente.empresa_id == e.id, models.Cliente.activo == True).count(),
            "catalogo":      db.query(models.CatalogoItem).filter(models.CatalogoItem.empresa_id == e.id, models.CatalogoItem.activo == True).count(),
            "presupuestos":  db.query(models.Presupuesto).filter(models.Presupuesto.empresa_id == e.id).count(),
        })
    return resultado


# ── Detalle empresa ───────────────────────────────────────────────────────────

@router.get("/empresa/{empresa_id}/detalle")
def detalle_empresa(empresa_id: int, request: Request, db: Session = Depends(get_db)):
    require_superadmin(request, db)
    e = db.query(models.Empresa).filter(models.Empresa.id == empresa_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    usuarios = db.query(models.Usuario).filter(models.Usuario.empresa_id == empresa_id).all()
    presupuestos = db.query(models.Presupuesto).filter(
        models.Presupuesto.empresa_id == empresa_id
    ).order_by(models.Presupuesto.created_at.desc()).limit(5).all()
    return {
        "empresa": {
            "id": e.id, "nombre": e.nombre, "email": e.email,
            "telefono": e.telefono or "", "nif": e.nif or "", "direccion": e.direccion or "",
        },
        "usuarios": [{"id": u.id, "nombre": u.nombre, "email": u.email,
                      "rol": u.rol, "activo": u.activo} for u in usuarios],
        "presupuestos_recientes": [
            {"numero": p.numero, "titulo": p.titulo, "estado": p.estado,
             "fecha": p.fecha.strftime("%d/%m/%Y") if p.fecha else ""}
            for p in presupuestos
        ],
    }


# ── Editar empresa ────────────────────────────────────────────────────────────

@router.put("/empresa/{empresa_id}")
def editar_empresa(empresa_id: int, data: dict, request: Request, db: Session = Depends(get_db)):
    require_superadmin(request, db)
    e = db.query(models.Empresa).filter(models.Empresa.id == empresa_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    for campo in ("nombre", "email", "telefono", "nif", "direccion"):
        if campo in data and data[campo] is not None:
            setattr(e, campo, data[campo])
    db.commit()
    return {"ok": True}


# ── Eliminar empresa ──────────────────────────────────────────────────────────

@router.delete("/empresa/{empresa_id}")
def eliminar_empresa(empresa_id: int, request: Request, db: Session = Depends(get_db)):
    require_superadmin(request, db)
    e = db.query(models.Empresa).filter(models.Empresa.id == empresa_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    if e.email == SISTEMA_EMAIL:
        raise HTTPException(status_code=400, detail="No se puede eliminar la empresa del sistema")
    # Eliminar en cascada
    db.query(models.LineaPresupuesto).filter(
        models.LineaPresupuesto.presupuesto_id.in_(
            db.query(models.Presupuesto.id).filter(models.Presupuesto.empresa_id == empresa_id)
        )
    ).delete(synchronize_session=False)
    db.query(models.Presupuesto).filter(models.Presupuesto.empresa_id == empresa_id).delete()
    db.query(models.Cliente).filter(models.Cliente.empresa_id == empresa_id).delete()
    db.query(models.CatalogoItem).filter(models.CatalogoItem.empresa_id == empresa_id).delete()
    db.query(models.Usuario).filter(models.Usuario.empresa_id == empresa_id).delete()
    db.delete(e)
    db.commit()
    return {"ok": True}


# ── Usuarios ──────────────────────────────────────────────────────────────────

@router.post("/empresa/{empresa_id}/usuario")
def crear_usuario(empresa_id: int, data: dict, request: Request, db: Session = Depends(get_db)):
    require_superadmin(request, db)
    if db.query(models.Usuario).filter(models.Usuario.email == data.get("email")).first():
        raise HTTPException(status_code=400, detail="Ya existe un usuario con ese email")
    u = models.Usuario(
        empresa_id=empresa_id,
        nombre=data["nombre"],
        email=data["email"],
        password_hash=hash_password(data["password"]),
        rol=data.get("rol", "operario"),
        activo=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"ok": True, "id": u.id}


@router.put("/empresa/{empresa_id}/usuario/{usuario_id}")
def editar_usuario(empresa_id: int, usuario_id: int, data: dict,
                   request: Request, db: Session = Depends(get_db)):
    require_superadmin(request, db)
    u = db.query(models.Usuario).filter(
        models.Usuario.id == usuario_id,
        models.Usuario.empresa_id == empresa_id
    ).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    for campo in ("nombre", "email", "rol"):
        if campo in data:
            setattr(u, campo, data[campo])
    db.commit()
    return {"ok": True}


@router.post("/empresa/{empresa_id}/usuario/{usuario_id}/password")
def cambiar_password(empresa_id: int, usuario_id: int, data: dict,
                     request: Request, db: Session = Depends(get_db)):
    require_superadmin(request, db)
    u = db.query(models.Usuario).filter(
        models.Usuario.id == usuario_id,
        models.Usuario.empresa_id == empresa_id
    ).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    nueva = data.get("password", "").strip()
    if len(nueva) < 4:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 4 caracteres")
    u.password_hash = hash_password(nueva)
    db.commit()
    return {"ok": True}


@router.post("/empresa/{empresa_id}/usuario/{usuario_id}/toggle")
def toggle_usuario(empresa_id: int, usuario_id: int, request: Request, db: Session = Depends(get_db)):
    require_superadmin(request, db)
    u = db.query(models.Usuario).filter(
        models.Usuario.id == usuario_id,
        models.Usuario.empresa_id == empresa_id
    ).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    u.activo = not u.activo
    db.commit()
    return {"ok": True, "activo": u.activo}


@router.delete("/empresa/{empresa_id}/usuario/{usuario_id}")
def eliminar_usuario(empresa_id: int, usuario_id: int, request: Request, db: Session = Depends(get_db)):
    require_superadmin(request, db)
    u = db.query(models.Usuario).filter(
        models.Usuario.id == usuario_id,
        models.Usuario.empresa_id == empresa_id
    ).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if u.rol == "superadmin":
        raise HTTPException(status_code=400, detail="No se puede eliminar un superadmin")
    db.delete(u)
    db.commit()
    return {"ok": True}


# ── Sesión (entrar/salir empresa) ─────────────────────────────────────────────

@router.post("/entrar/{empresa_id}")
def entrar_empresa(empresa_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    require_superadmin(request, db)
    empresa = db.query(models.Empresa).filter(models.Empresa.id == empresa_id).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    response.set_cookie(key="view_empresa_id", value=str(empresa_id), max_age=3600, **_cookie_opts())
    return {"ok": True, "empresa": empresa.nombre}


@router.post("/salir")
def salir_empresa(request: Request, response: Response, db: Session = Depends(get_db)):
    require_superadmin(request, db)
    response.delete_cookie("view_empresa_id")
    return {"ok": True}

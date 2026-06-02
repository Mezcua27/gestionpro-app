from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.auth import require_superadmin

router = APIRouter()


@router.get("/empresas")
def listar_empresas(request: Request, db: Session = Depends(get_db)):
    require_superadmin(request, db)
    empresas = db.query(models.Empresa).order_by(models.Empresa.created_at.desc()).all()
    resultado = []
    for e in empresas:
        usuarios = db.query(models.Usuario).filter(models.Usuario.empresa_id == e.id).count()
        clientes = db.query(models.Cliente).filter(
            models.Cliente.empresa_id == e.id, models.Cliente.activo == True).count()
        catalogo = db.query(models.CatalogoItem).filter(
            models.CatalogoItem.empresa_id == e.id, models.CatalogoItem.activo == True).count()
        presupuestos = db.query(models.Presupuesto).filter(
            models.Presupuesto.empresa_id == e.id).count()
        resultado.append({
            "id": e.id,
            "nombre": e.nombre,
            "email": e.email,
            "telefono": e.telefono,
            "nif": e.nif,
            "created_at": e.created_at.strftime("%d/%m/%Y") if e.created_at else "",
            "usuarios": usuarios,
            "clientes": clientes,
            "catalogo": catalogo,
            "presupuestos": presupuestos,
        })
    return resultado


@router.post("/entrar/{empresa_id}")
def entrar_empresa(empresa_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    require_superadmin(request, db)
    empresa = db.query(models.Empresa).filter(models.Empresa.id == empresa_id).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    import os
    es_produccion = not os.getenv("DATABASE_URL", "sqlite").startswith("sqlite")
    response.set_cookie(
        key="view_empresa_id", value=str(empresa_id),
        httponly=True, max_age=3600, samesite="lax", secure=es_produccion
    )
    return {"ok": True, "empresa": empresa.nombre}


@router.post("/salir")
def salir_empresa(request: Request, response: Response, db: Session = Depends(get_db)):
    require_superadmin(request, db)
    response.delete_cookie("view_empresa_id")
    return {"ok": True}


@router.get("/empresa/{empresa_id}/detalle")
def detalle_empresa(empresa_id: int, request: Request, db: Session = Depends(get_db)):
    require_superadmin(request, db)
    e = db.query(models.Empresa).filter(models.Empresa.id == empresa_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    usuarios = db.query(models.Usuario).filter(models.Usuario.empresa_id == empresa_id).all()
    presupuestos_recientes = db.query(models.Presupuesto).filter(
        models.Presupuesto.empresa_id == empresa_id
    ).order_by(models.Presupuesto.created_at.desc()).limit(5).all()

    return {
        "empresa": {"id": e.id, "nombre": e.nombre, "email": e.email,
                    "telefono": e.telefono, "nif": e.nif, "direccion": e.direccion},
        "usuarios": [{"id": u.id, "nombre": u.nombre, "email": u.email,
                      "rol": u.rol, "activo": u.activo} for u in usuarios],
        "presupuestos_recientes": [
            {"numero": p.numero, "titulo": p.titulo,
             "estado": p.estado, "fecha": p.fecha.strftime("%d/%m/%Y") if p.fecha else ""}
            for p in presupuestos_recientes
        ],
    }


@router.delete("/empresa/{empresa_id}/usuario/{usuario_id}")
def desactivar_usuario(empresa_id: int, usuario_id: int, request: Request, db: Session = Depends(get_db)):
    require_superadmin(request, db)
    u = db.query(models.Usuario).filter(
        models.Usuario.id == usuario_id,
        models.Usuario.empresa_id == empresa_id
    ).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    u.activo = False
    db.commit()
    return {"ok": True}


@router.post("/empresa/{empresa_id}/usuario/{usuario_id}/activar")
def activar_usuario(empresa_id: int, usuario_id: int, request: Request, db: Session = Depends(get_db)):
    require_superadmin(request, db)
    u = db.query(models.Usuario).filter(
        models.Usuario.id == usuario_id,
        models.Usuario.empresa_id == empresa_id
    ).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    u.activo = True
    db.commit()
    return {"ok": True}

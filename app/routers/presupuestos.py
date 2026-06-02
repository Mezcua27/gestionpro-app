import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
from io import BytesIO
from app.database import get_db
from app import models, schemas
from app.auth import get_current_user

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generar_numero(empresa_id: int, db: Session) -> str:
    year = datetime.utcnow().year
    count = db.query(models.Presupuesto).filter(
        models.Presupuesto.empresa_id == empresa_id
    ).count() + 1
    return f"PRES-{year}-{count:04d}"


def _check_anulados(db: Session, empresa_id: int = None):
    """Marca como 'anulado' los presupuestos caducados que aún están pendientes."""
    ahora = datetime.utcnow()
    q = db.query(models.Presupuesto).filter(
        models.Presupuesto.estado.notin_(["aceptado", "rechazado", "anulado"])
    )
    if empresa_id:
        q = q.filter(models.Presupuesto.empresa_id == empresa_id)
    pendientes = q.all()
    cambiados = 0
    for p in pendientes:
        fecha_base = p.fecha or p.created_at
        if fecha_base and (ahora - fecha_base) > timedelta(days=p.validez_dias):
            p.estado = "anulado"
            cambiados += 1
    if cambiados:
        db.commit()


# ── CRUD presupuesto ──────────────────────────────────────────────────────────

@router.get("/", response_model=List[schemas.PresupuestoResponse])
def listar(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    _check_anulados(db, user.empresa_id)
    return db.query(models.Presupuesto).filter(
        models.Presupuesto.empresa_id == user.empresa_id
    ).order_by(models.Presupuesto.created_at.desc()).all()


@router.get("/{id}", response_model=schemas.PresupuestoResponse)
def obtener(id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    p = db.query(models.Presupuesto).filter(
        models.Presupuesto.id == id,
        models.Presupuesto.empresa_id == user.empresa_id
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    _check_anulados(db, user.empresa_id)
    db.refresh(p)
    return p


@router.post("/", response_model=schemas.PresupuestoResponse)
def crear(data: schemas.PresupuestoCreate, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if data.cliente_id:
        c = db.query(models.Cliente).filter(
            models.Cliente.id == data.cliente_id,
            models.Cliente.empresa_id == user.empresa_id
        ).first()
        if not c:
            raise HTTPException(status_code=400, detail="Cliente no válido")

    p = models.Presupuesto(
        **data.dict(),
        empresa_id=user.empresa_id,
        numero=_generar_numero(user.empresa_id, db),
        creado_por=user.id,
        token_cliente=secrets.token_urlsafe(32),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.put("/{id}", response_model=schemas.PresupuestoResponse)
def actualizar(id: int, data: schemas.PresupuestoUpdate, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    p = db.query(models.Presupuesto).filter(
        models.Presupuesto.id == id,
        models.Presupuesto.empresa_id == user.empresa_id
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    for k, v in data.dict(exclude_none=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{id}")
def eliminar(id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    p = db.query(models.Presupuesto).filter(
        models.Presupuesto.id == id,
        models.Presupuesto.empresa_id == user.empresa_id
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    db.delete(p)
    db.commit()
    return {"ok": True}


# ── Líneas ────────────────────────────────────────────────────────────────────

@router.post("/{id}/lineas", response_model=schemas.LineaResponse)
def añadir_linea(id: int, data: schemas.LineaCreate, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    p = db.query(models.Presupuesto).filter(
        models.Presupuesto.id == id,
        models.Presupuesto.empresa_id == user.empresa_id
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    linea = models.LineaPresupuesto(**data.dict(), presupuesto_id=id)
    db.add(linea)
    db.commit()
    db.refresh(linea)
    return linea


@router.put("/{presupuesto_id}/lineas/{linea_id}", response_model=schemas.LineaResponse)
def editar_linea(presupuesto_id: int, linea_id: int, data: schemas.LineaUpdate,
                 request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    p = db.query(models.Presupuesto).filter(
        models.Presupuesto.id == presupuesto_id,
        models.Presupuesto.empresa_id == user.empresa_id
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    linea = db.query(models.LineaPresupuesto).filter(
        models.LineaPresupuesto.id == linea_id,
        models.LineaPresupuesto.presupuesto_id == presupuesto_id
    ).first()
    if not linea:
        raise HTTPException(status_code=404, detail="Línea no encontrada")
    for k, v in data.dict(exclude_none=True).items():
        setattr(linea, k, v)
    db.commit()
    db.refresh(linea)
    return linea


@router.post("/{id}/lineas/bulk")
def añadir_lineas_bulk(id: int, lineas: List[schemas.LineaCreate], request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    p = db.query(models.Presupuesto).filter(
        models.Presupuesto.id == id,
        models.Presupuesto.empresa_id == user.empresa_id
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    orden_base = len(p.lineas)
    for i, l in enumerate(lineas):
        nueva = models.LineaPresupuesto(**l.dict(), presupuesto_id=id, orden=orden_base + i)
        db.add(nueva)
    db.commit()
    db.refresh(p)
    return {"ok": True, "añadidas": len(lineas)}


@router.delete("/{presupuesto_id}/lineas/{linea_id}")
def eliminar_linea(presupuesto_id: int, linea_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    p = db.query(models.Presupuesto).filter(
        models.Presupuesto.id == presupuesto_id,
        models.Presupuesto.empresa_id == user.empresa_id
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    linea = db.query(models.LineaPresupuesto).filter(
        models.LineaPresupuesto.id == linea_id,
        models.LineaPresupuesto.presupuesto_id == presupuesto_id
    ).first()
    if not linea:
        raise HTTPException(status_code=404, detail="Línea no encontrada")
    db.delete(linea)
    db.commit()
    return {"ok": True}


# ── PDF ───────────────────────────────────────────────────────────────────────

@router.get("/{id}/pdf")
def descargar_pdf(id: int, request: Request, db: Session = Depends(get_db)):
    from app.pdf_generator import generar_pdf
    user = get_current_user(request, db)
    p = db.query(models.Presupuesto).filter(
        models.Presupuesto.id == id,
        models.Presupuesto.empresa_id == user.empresa_id
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    empresa = db.query(models.Empresa).filter(models.Empresa.id == user.empresa_id).first()
    pdf_bytes = generar_pdf(p, empresa, p.cliente)
    nombre = f"{p.numero.replace('/', '-')}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nombre}"}
    )


# ── Endpoints públicos del cliente (sin autenticación) ────────────────────────

@router.get("/cliente/{token}")
def ver_presupuesto_cliente(token: str, db: Session = Depends(get_db)):
    """Devuelve los datos públicos del presupuesto para el cliente."""
    p = db.query(models.Presupuesto).filter(
        models.Presupuesto.token_cliente == token
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    # Marcar como visto la primera vez
    if not p.fecha_lectura:
        p.fecha_lectura = datetime.utcnow()
        if p.estado == "enviado":
            p.estado = "visto"
        db.commit()
        db.refresh(p)

    ahora = datetime.utcnow()
    fecha_base = p.fecha or p.created_at
    expirado = bool(fecha_base and (ahora - fecha_base) > timedelta(days=p.validez_dias))
    if expirado and p.estado not in ("aceptado", "rechazado", "anulado"):
        p.estado = "anulado"
        db.commit()

    empresa = db.query(models.Empresa).filter(models.Empresa.id == p.empresa_id).first()
    total_base = sum(l.cantidad * l.precio_unitario for l in p.lineas)
    total_dto  = total_base * (p.descuento / 100)
    total_iva  = (total_base - total_dto) * (p.iva / 100)
    total_final = total_base - total_dto + total_iva

    fecha_vencimiento = None
    if fecha_base:
        fecha_vencimiento = (fecha_base + timedelta(days=p.validez_dias)).strftime("%d/%m/%Y")

    return {
        "id": p.id,
        "numero": p.numero,
        "titulo": p.titulo,
        "estado": p.estado,
        "fecha": p.fecha.strftime("%d/%m/%Y") if p.fecha else "",
        "fecha_vencimiento": fecha_vencimiento,
        "validez_dias": p.validez_dias,
        "descuento": p.descuento,
        "iva": p.iva,
        "notas": p.notas,
        "expirado": expirado,
        "fecha_lectura": p.fecha_lectura.strftime("%d/%m/%Y %H:%M") if p.fecha_lectura else None,
        "fecha_aceptacion": p.fecha_aceptacion.strftime("%d/%m/%Y %H:%M") if p.fecha_aceptacion else None,
        "empresa": {"nombre": empresa.nombre, "telefono": empresa.telefono, "email": empresa.email},
        "cliente": {"nombre": p.cliente.nombre if p.cliente else None},
        "lineas": [
            {"tipo": l.tipo, "descripcion": l.descripcion,
             "cantidad": l.cantidad, "precio_unitario": l.precio_unitario,
             "total": l.cantidad * l.precio_unitario}
            for l in p.lineas
        ],
        "total_base": total_base,
        "total_dto": total_dto,
        "total_iva": total_iva,
        "total_final": total_final,
    }


@router.post("/cliente/{token}/accion")
def accion_cliente(token: str, data: dict, db: Session = Depends(get_db)):
    """El cliente acepta o rechaza el presupuesto."""
    accion = data.get("accion")  # "aceptar" | "rechazar"
    if accion not in ("aceptar", "rechazar"):
        raise HTTPException(status_code=400, detail="Acción no válida")

    p = db.query(models.Presupuesto).filter(
        models.Presupuesto.token_cliente == token
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    if p.estado in ("aceptado", "rechazado", "anulado"):
        raise HTTPException(status_code=400, detail=f"El presupuesto ya está en estado '{p.estado}'")

    ahora = datetime.utcnow()
    fecha_base = p.fecha or p.created_at
    if fecha_base and (ahora - fecha_base) > timedelta(days=p.validez_dias):
        p.estado = "anulado"
        db.commit()
        raise HTTPException(status_code=400, detail="El plazo de aceptación ha vencido")

    p.estado = "aceptado" if accion == "aceptar" else "rechazado"
    p.fecha_aceptacion = ahora
    db.commit()
    return {"ok": True, "estado": p.estado}

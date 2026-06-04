import secrets
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, get_effective_empresa_id

router = APIRouter()


def _get_plantilla(id: int, eid: int, db: Session) -> models.PlantillaPresupuesto:
    p = db.query(models.PlantillaPresupuesto).filter(
        models.PlantillaPresupuesto.id == id,
        models.PlantillaPresupuesto.empresa_id == eid
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return p


# ── CRUD plantillas ───────────────────────────────────────────────────────────

@router.get("/", response_model=List[schemas.PlantillaResponse])
def listar(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    eid = get_effective_empresa_id(user, request)
    return db.query(models.PlantillaPresupuesto).filter(
        models.PlantillaPresupuesto.empresa_id == eid
    ).order_by(models.PlantillaPresupuesto.nombre).all()


@router.get("/{id}", response_model=schemas.PlantillaResponse)
def obtener(id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    eid = get_effective_empresa_id(user, request)
    return _get_plantilla(id, eid, db)


@router.post("/", response_model=schemas.PlantillaResponse)
def crear(data: schemas.PlantillaCreate, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    eid = get_effective_empresa_id(user, request)
    p = models.PlantillaPresupuesto(**data.dict(), empresa_id=eid)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.put("/{id}", response_model=schemas.PlantillaResponse)
def actualizar(id: int, data: schemas.PlantillaUpdate, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    eid = get_effective_empresa_id(user, request)
    p = _get_plantilla(id, eid, db)
    for k, v in data.dict(exclude_none=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{id}")
def eliminar(id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    eid = get_effective_empresa_id(user, request)
    p = _get_plantilla(id, eid, db)
    db.delete(p)
    db.commit()
    return {"ok": True}


# ── Líneas de plantilla ───────────────────────────────────────────────────────

@router.post("/{id}/lineas", response_model=schemas.LineaPlantillaResponse)
def añadir_linea(id: int, data: schemas.LineaPlantillaCreate, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    eid = get_effective_empresa_id(user, request)
    _get_plantilla(id, eid, db)
    linea = models.LineaPlantilla(**data.dict(), plantilla_id=id)
    db.add(linea)
    db.commit()
    db.refresh(linea)
    return linea


@router.post("/{id}/lineas/bulk")
def añadir_lineas_bulk(id: int, lineas: List[schemas.LineaPlantillaCreate], request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    eid = get_effective_empresa_id(user, request)
    p = _get_plantilla(id, eid, db)
    orden_base = len(p.lineas)
    for i, l in enumerate(lineas):
        datos = l.dict()
        datos['orden'] = orden_base + i
        db.add(models.LineaPlantilla(**datos, plantilla_id=id))
    db.commit()
    db.refresh(p)
    return {"ok": True, "añadidas": len(lineas)}


@router.put("/{id}/lineas/{linea_id}", response_model=schemas.LineaPlantillaResponse)
def editar_linea(id: int, linea_id: int, data: schemas.LineaPlantillaUpdate,
                 request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    eid = get_effective_empresa_id(user, request)
    _get_plantilla(id, eid, db)
    linea = db.query(models.LineaPlantilla).filter(
        models.LineaPlantilla.id == linea_id,
        models.LineaPlantilla.plantilla_id == id
    ).first()
    if not linea:
        raise HTTPException(status_code=404, detail="Línea no encontrada")
    for k, v in data.dict(exclude_none=True).items():
        setattr(linea, k, v)
    db.commit()
    db.refresh(linea)
    return linea


@router.delete("/{id}/lineas/{linea_id}")
def eliminar_linea(id: int, linea_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    eid = get_effective_empresa_id(user, request)
    _get_plantilla(id, eid, db)
    linea = db.query(models.LineaPlantilla).filter(
        models.LineaPlantilla.id == linea_id,
        models.LineaPlantilla.plantilla_id == id
    ).first()
    if not linea:
        raise HTTPException(status_code=404, detail="Línea no encontrada")
    db.delete(linea)
    db.commit()
    return {"ok": True}


# ── Usar plantilla → crear presupuesto ───────────────────────────────────────

@router.post("/{id}/usar", response_model=schemas.PresupuestoResponse)
def usar_plantilla(id: int, data: dict, request: Request, db: Session = Depends(get_db)):
    """Crea un nuevo presupuesto en borrador a partir de esta plantilla."""
    user = get_current_user(request, db)
    eid = get_effective_empresa_id(user, request)
    plantilla = _get_plantilla(id, eid, db)

    cliente_id = data.get("cliente_id")
    if cliente_id:
        c = db.query(models.Cliente).filter(
            models.Cliente.id == cliente_id,
            models.Cliente.empresa_id == eid
        ).first()
        if not c:
            raise HTTPException(status_code=400, detail="Cliente no válido")

    # Generar número correlativo
    year = datetime.utcnow().year
    count = db.query(models.Presupuesto).filter(
        models.Presupuesto.empresa_id == eid
    ).count() + 1
    numero = f"PRES-{year}-{count:04d}"

    titulo = data.get("titulo") or plantilla.nombre
    pres = models.Presupuesto(
        empresa_id=eid,
        cliente_id=cliente_id,
        numero=numero,
        titulo=titulo,
        estado="borrador",
        validez_dias=plantilla.validez_dias,
        notas=plantilla.notas,
        descuento=plantilla.descuento,
        iva=plantilla.iva,
        creado_por=user.id,
        token_cliente=secrets.token_urlsafe(32),
    )
    db.add(pres)
    db.flush()

    for i, l in enumerate(plantilla.lineas):
        db.add(models.LineaPresupuesto(
            presupuesto_id=pres.id,
            tipo=l.tipo,
            descripcion=l.descripcion,
            cantidad=l.cantidad,
            precio_unitario=l.precio_unitario,
            unidad=l.unidad,
            referencia=l.referencia,
            orden=i,
        ))

    db.commit()
    db.refresh(pres)
    return pres

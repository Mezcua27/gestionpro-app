from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, get_effective_empresa_id

router = APIRouter()


@router.get("/", response_model=List[schemas.ClienteResponse])
def listar(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    eid = get_effective_empresa_id(user, request)
    return db.query(models.Cliente).filter(
        models.Cliente.empresa_id == eid,
        models.Cliente.activo == True
    ).order_by(models.Cliente.nombre).all()


@router.get("/{id}", response_model=schemas.ClienteResponse)
def obtener(id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    eid = get_effective_empresa_id(user, request)
    c = db.query(models.Cliente).filter(
        models.Cliente.id == id,
        models.Cliente.empresa_id == eid
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return c


@router.post("/", response_model=schemas.ClienteResponse)
def crear(data: schemas.ClienteCreate, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    eid = get_effective_empresa_id(user, request)
    cliente = models.Cliente(**data.dict(), empresa_id=eid)
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


@router.put("/{id}", response_model=schemas.ClienteResponse)
def actualizar(id: int, data: schemas.ClienteCreate, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    eid = get_effective_empresa_id(user, request)
    c = db.query(models.Cliente).filter(
        models.Cliente.id == id,
        models.Cliente.empresa_id == eid
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    for k, v in data.dict().items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{id}")
def eliminar(id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    eid = get_effective_empresa_id(user, request)
    c = db.query(models.Cliente).filter(
        models.Cliente.id == id,
        models.Cliente.empresa_id == eid
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    c.activo = False
    db.commit()
    return {"ok": True}

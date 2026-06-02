from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas
from app.auth import verify_password, hash_password, create_token, get_current_user

router = APIRouter()


@router.post("/registro")
def registrar_empresa(data: schemas.EmpresaCreate, db: Session = Depends(get_db)):
    if db.query(models.Empresa).filter(models.Empresa.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email de empresa ya registrado")
    if db.query(models.Usuario).filter(models.Usuario.email == data.admin_email).first():
        raise HTTPException(status_code=400, detail="Email de usuario ya registrado")

    empresa = models.Empresa(
        nombre=data.nombre, email=data.email,
        telefono=data.telefono, nif=data.nif
    )
    db.add(empresa)
    db.flush()

    admin = models.Usuario(
        empresa_id=empresa.id,
        nombre=data.admin_nombre,
        email=data.admin_email,
        password_hash=hash_password(data.admin_password),
        rol="admin"
    )
    db.add(admin)
    db.commit()
    return {"ok": True, "message": "Empresa registrada correctamente"}


@router.post("/login")
def login(data: schemas.LoginForm, response: Response, db: Session = Depends(get_db)):
    user = db.query(models.Usuario).filter(
        models.Usuario.email == data.email,
        models.Usuario.activo == True
    ).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    token = create_token({"sub": str(user.id), "empresa_id": user.empresa_id})
    response.set_cookie(
        key="access_token", value=token,
        httponly=True, max_age=7 * 24 * 3600, samesite="lax"
    )
    return {"ok": True, "nombre": user.nombre, "rol": user.rol}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"ok": True}


@router.get("/me")
def get_me(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return {
        "id": user.id, "nombre": user.nombre,
        "email": user.email, "rol": user.rol,
        "empresa_id": user.empresa_id
    }

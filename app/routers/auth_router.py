import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas
from app.auth import verify_password, hash_password, create_token, get_current_user
from app.email_service import email_recuperar_password, smtp_configurado

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
    import os
    es_produccion = not os.getenv("DATABASE_URL", "sqlite").startswith("sqlite")
    response.set_cookie(
        key="access_token", value=token,
        httponly=True, max_age=7 * 24 * 3600,
        samesite="lax", secure=es_produccion
    )
    return {"ok": True, "nombre": user.nombre, "rol": user.rol}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"ok": True}


@router.post("/recuperar-password")
def solicitar_recuperacion(data: dict, request: Request, db: Session = Depends(get_db)):
    """Genera un token de reset y envía email (o devuelve el enlace en dev)."""
    email = data.get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email requerido")

    user = db.query(models.Usuario).filter(
        models.Usuario.email == email,
        models.Usuario.activo == True
    ).first()

    # Siempre respuesta genérica para no revelar si el email existe
    respuesta_generica = {"ok": True, "mensaje": "Si el email está registrado recibirás un enlace en breve."}

    if not user:
        return respuesta_generica

    # Invalidar tokens anteriores del usuario
    db.query(models.ResetToken).filter(
        models.ResetToken.usuario_id == user.id,
        models.ResetToken.usado == False
    ).update({"usado": True})

    token = secrets.token_urlsafe(48)
    reset = models.ResetToken(
        usuario_id=user.id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    db.add(reset)
    db.commit()

    base_url = str(request.base_url).rstrip("/")
    enlace = f"{base_url}/restablecer/{token}"

    if smtp_configurado():
        email_recuperar_password(user.email, user.nombre, enlace)
        return respuesta_generica
    else:
        # Sin SMTP configurado: devolver el enlace directamente (modo dev/sin email)
        return {
            "ok": True,
            "sin_smtp": True,
            "enlace": enlace,
            "mensaje": "SMTP no configurado. Usa el enlace para restablecer la contraseña."
        }


@router.post("/restablecer-password")
def restablecer_password(data: dict, db: Session = Depends(get_db)):
    token_str  = data.get("token", "").strip()
    nueva      = data.get("password", "").strip()

    if not token_str or not nueva:
        raise HTTPException(status_code=400, detail="Token y contraseña son requeridos")
    if len(nueva) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres")

    reset = db.query(models.ResetToken).filter(
        models.ResetToken.token == token_str,
        models.ResetToken.usado == False
    ).first()

    if not reset:
        raise HTTPException(status_code=400, detail="Enlace no válido o ya utilizado")
    if reset.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="El enlace ha expirado. Solicita uno nuevo.")

    reset.usuario.password_hash = hash_password(nueva)
    reset.usado = True
    db.commit()
    return {"ok": True, "mensaje": "Contraseña actualizada correctamente"}


@router.get("/me")
def get_me(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return {
        "id": user.id, "nombre": user.nombre,
        "email": user.email, "rol": user.rol,
        "empresa_id": user.empresa_id
    }

import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app import models

SECRET_KEY = os.getenv("SECRET_KEY", "cambia-esta-clave-secreta-en-produccion-2024")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24 * 7  # 7 días


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def create_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    payload = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=TOKEN_EXPIRE_HOURS))
    payload.update({"exp": expire})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> models.Usuario:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")

    user = db.query(models.Usuario).filter(
        models.Usuario.id == int(user_id),
        models.Usuario.activo == True
    ).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user


def require_admin(request: Request, db: Session = Depends(get_db)) -> models.Usuario:
    user = get_current_user(request, db)
    if user.rol not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Se requieren permisos de administrador")
    return user


def require_superadmin(request: Request, db: Session = Depends(get_db)) -> models.Usuario:
    user = get_current_user(request, db)
    if user.rol != "superadmin":
        raise HTTPException(status_code=403, detail="Acceso restringido a superadmin")
    return user


def get_effective_empresa_id(user: models.Usuario, request: Request) -> int:
    """Para superadmin: devuelve la empresa que está visitando (si la hay), si no la suya."""
    if user.rol == "superadmin":
        view_id = request.cookies.get("view_empresa_id")
        if view_id:
            try:
                return int(view_id)
            except ValueError:
                pass
    return user.empresa_id

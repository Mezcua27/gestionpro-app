import os
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.database import engine, get_db
from app import models
from app.auth import get_current_user
from app.routers import auth_router, catalogo, clientes, presupuestos, usuarios, asistente

load_dotenv()

models.Base.metadata.create_all(bind=engine)

# Migraciones automáticas de columnas nuevas (SQLite + PostgreSQL)
with engine.connect() as conn:
    from sqlalchemy import text, inspect
    from app.database import IS_SQLITE
    inspector = inspect(engine)

    def _add_col(tabla, columna, tipo_sqlite, tipo_pg=None):
        cols = [c["name"] for c in inspector.get_columns(tabla)]
        if columna in cols:
            return
        tipo = tipo_sqlite if IS_SQLITE else (tipo_pg or tipo_sqlite)
        if IS_SQLITE:
            conn.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}"))
        else:
            conn.execute(text(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {columna} {tipo}"))
        conn.commit()

    _add_col("catalogo",      "foto",             "VARCHAR")
    _add_col("presupuestos",  "token_cliente",     "VARCHAR")
    _add_col("presupuestos",  "fecha_lectura",     "DATETIME",  "TIMESTAMP")
    _add_col("presupuestos",  "fecha_aceptacion",  "DATETIME",  "TIMESTAMP")

    # Generar token_cliente para presupuestos existentes sin token
    import secrets as _secrets
    rows = conn.execute(text("SELECT id FROM presupuestos WHERE token_cliente IS NULL")).fetchall()
    for row in rows:
        tok = _secrets.token_urlsafe(32)
        conn.execute(text("UPDATE presupuestos SET token_cliente=:t WHERE id=:i"), {"t": tok, "i": row[0]})
    if rows:
        conn.commit()

app = FastAPI(title="Gestión Empresarial")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
# Añadir timedelta al entorno Jinja2 para calcular fechas en templates
from datetime import timedelta as _timedelta
templates.env.globals["timedelta"] = _timedelta
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(os.path.join(STATIC_DIR, "uploads", "catalogo"), exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(auth_router.router, prefix="/auth", tags=["Auth"])
app.include_router(catalogo.router, prefix="/api/catalogo", tags=["Catálogo"])
app.include_router(clientes.router, prefix="/api/clientes", tags=["Clientes"])
app.include_router(presupuestos.router, prefix="/api/presupuestos", tags=["Presupuestos"])
app.include_router(usuarios.router, prefix="/api/usuarios", tags=["Usuarios"])
app.include_router(asistente.router, prefix="/api/asistente", tags=["Asistente IA"])


def _user_or_redirect(request: Request, db: Session):
    try:
        return get_current_user(request, db)
    except Exception:
        return None


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    token = request.cookies.get("access_token")
    return RedirectResponse(url="/dashboard" if token else "/login")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/registro", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("registro.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    user = _user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login")

    total_clientes = db.query(models.Cliente).filter(
        models.Cliente.empresa_id == user.empresa_id,
        models.Cliente.activo == True
    ).count()
    total_catalogo = db.query(models.CatalogoItem).filter(
        models.CatalogoItem.empresa_id == user.empresa_id,
        models.CatalogoItem.activo == True
    ).count()
    total_presupuestos = db.query(models.Presupuesto).filter(
        models.Presupuesto.empresa_id == user.empresa_id
    ).count()
    recientes = db.query(models.Presupuesto).filter(
        models.Presupuesto.empresa_id == user.empresa_id
    ).order_by(models.Presupuesto.created_at.desc()).limit(5).all()

    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user,
        "total_clientes": total_clientes,
        "total_catalogo": total_catalogo,
        "total_presupuestos": total_presupuestos,
        "recientes": recientes,
    })


@app.get("/catalogo", response_class=HTMLResponse)
def catalogo_page(request: Request, db: Session = Depends(get_db)):
    user = _user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login")
    items = db.query(models.CatalogoItem).filter(
        models.CatalogoItem.empresa_id == user.empresa_id,
        models.CatalogoItem.activo == True
    ).order_by(models.CatalogoItem.tipo, models.CatalogoItem.descripcion).all()
    return templates.TemplateResponse("catalogo.html", {"request": request, "user": user, "items": items})


@app.get("/clientes", response_class=HTMLResponse)
def clientes_page(request: Request, db: Session = Depends(get_db)):
    user = _user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login")
    lista = db.query(models.Cliente).filter(
        models.Cliente.empresa_id == user.empresa_id,
        models.Cliente.activo == True
    ).order_by(models.Cliente.nombre).all()
    return templates.TemplateResponse("clientes.html", {"request": request, "user": user, "clientes": lista})


@app.get("/presupuestos", response_class=HTMLResponse)
def presupuestos_page(request: Request, db: Session = Depends(get_db)):
    user = _user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login")
    lista = db.query(models.Presupuesto).filter(
        models.Presupuesto.empresa_id == user.empresa_id
    ).order_by(models.Presupuesto.created_at.desc()).all()
    clientes_lista = db.query(models.Cliente).filter(
        models.Cliente.empresa_id == user.empresa_id,
        models.Cliente.activo == True
    ).order_by(models.Cliente.nombre).all()
    return templates.TemplateResponse("presupuestos.html", {
        "request": request, "user": user,
        "presupuestos": lista, "clientes": clientes_lista
    })


@app.get("/presupuestos/{id}", response_class=HTMLResponse)
def presupuesto_detail(id: int, request: Request, db: Session = Depends(get_db)):
    user = _user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login")
    p = db.query(models.Presupuesto).filter(
        models.Presupuesto.id == id,
        models.Presupuesto.empresa_id == user.empresa_id
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    clientes_lista = db.query(models.Cliente).filter(
        models.Cliente.empresa_id == user.empresa_id,
        models.Cliente.activo == True
    ).order_by(models.Cliente.nombre).all()
    return templates.TemplateResponse("presupuesto_detail.html", {
        "request": request, "user": user,
        "p": p, "clientes": clientes_lista
    })


@app.get("/ver/{token}", response_class=HTMLResponse)
def ver_presupuesto_cliente(token: str, request: Request):
    """Página pública para que el cliente vea y acepte/rechace el presupuesto."""
    return templates.TemplateResponse("presupuesto_cliente.html", {"request": request, "token": token})


@app.get("/usuarios", response_class=HTMLResponse)
def usuarios_page(request: Request, db: Session = Depends(get_db)):
    user = _user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login")
    if user.rol != "admin":
        return RedirectResponse(url="/dashboard")
    lista = db.query(models.Usuario).filter(
        models.Usuario.empresa_id == user.empresa_id
    ).order_by(models.Usuario.nombre).all()
    return templates.TemplateResponse("usuarios.html", {"request": request, "user": user, "usuarios": lista})

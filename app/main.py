import os
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.database import engine, get_db
from app import models
from app.auth import get_current_user, get_effective_empresa_id
from app.routers import auth_router, catalogo, clientes, presupuestos, usuarios, asistente, superadmin, empresa

load_dotenv()

models.Base.metadata.create_all(bind=engine)  # crea reset_tokens si no existe

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

    _add_col("catalogo",             "foto",               "VARCHAR")
    _add_col("catalogo",             "marca",              "VARCHAR")
    _add_col("presupuestos",         "token_cliente",      "VARCHAR")
    _add_col("presupuestos",         "fecha_lectura",      "DATETIME",  "TIMESTAMP")
    _add_col("presupuestos",         "fecha_aceptacion",   "DATETIME",  "TIMESTAMP")
    _add_col("empresas",             "logo",                   "TEXT")
    _add_col("empresas",             "color_corporativo",       "VARCHAR")
    _add_col("empresas",             "condiciones_generales",   "TEXT")
    _add_col("lineas_presupuesto",   "unidad",                  "VARCHAR")
    _add_col("lineas_presupuesto",   "referencia",              "VARCHAR")

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
os.makedirs(os.path.join(STATIC_DIR, "uploads", "logos"), exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(auth_router.router,   prefix="/auth",              tags=["Auth"])
app.include_router(catalogo.router,      prefix="/api/catalogo",      tags=["Catálogo"])
app.include_router(clientes.router,      prefix="/api/clientes",      tags=["Clientes"])
app.include_router(presupuestos.router,  prefix="/api/presupuestos",  tags=["Presupuestos"])
app.include_router(usuarios.router,      prefix="/api/usuarios",      tags=["Usuarios"])
app.include_router(asistente.router,     prefix="/api/asistente",     tags=["Asistente IA"])
app.include_router(superadmin.router,    prefix="/api/superadmin",    tags=["Superadmin"])
app.include_router(empresa.router,       prefix="/api/empresa",       tags=["Empresa"])


def _user_or_redirect(request: Request, db: Session):
    try:
        return get_current_user(request, db)
    except Exception:
        return None


@app.get("/health")
def health():
    return {"status": "ok", "v": "d0179f0"}


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


@app.get("/recuperar", response_class=HTMLResponse)
def recuperar_page(request: Request):
    return templates.TemplateResponse("recuperar.html", {"request": request})


@app.get("/restablecer/{token}", response_class=HTMLResponse)
def restablecer_page(token: str, request: Request):
    return templates.TemplateResponse("restablecer.html", {"request": request, "token": token})


@app.get("/superadmin", response_class=HTMLResponse)
def superadmin_page(request: Request, db: Session = Depends(get_db)):
    user = _user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login")
    if user.rol != "superadmin":
        return RedirectResponse(url="/dashboard")
    total_empresas = db.query(models.Empresa).count()
    total_usuarios = db.query(models.Usuario).filter(models.Usuario.activo == True).count()
    total_presupuestos = db.query(models.Presupuesto).count()
    return templates.TemplateResponse("superadmin.html", {
        "request": request, "user": user,
        "total_empresas": total_empresas,
        "total_usuarios": total_usuarios,
        "total_presupuestos": total_presupuestos,
    })


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    user = _user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login")
    if user.rol == "superadmin" and not request.cookies.get("view_empresa_id"):
        return RedirectResponse(url="/superadmin")

    eid = get_effective_empresa_id(user, request)
    empresa_vista = db.query(models.Empresa).filter(models.Empresa.id == eid).first() if user.rol == "superadmin" else None

    total_clientes = db.query(models.Cliente).filter(
        models.Cliente.empresa_id == eid, models.Cliente.activo == True).count()
    total_catalogo = db.query(models.CatalogoItem).filter(
        models.CatalogoItem.empresa_id == eid, models.CatalogoItem.activo == True).count()
    total_presupuestos = db.query(models.Presupuesto).filter(
        models.Presupuesto.empresa_id == eid).count()
    recientes = db.query(models.Presupuesto).filter(
        models.Presupuesto.empresa_id == eid
    ).order_by(models.Presupuesto.created_at.desc()).limit(5).all()

    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user,
        "empresa_vista": empresa_vista,
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
    eid = get_effective_empresa_id(user, request)
    empresa_vista = db.query(models.Empresa).filter(models.Empresa.id == eid).first() if user.rol == "superadmin" else None
    items = db.query(models.CatalogoItem).filter(
        models.CatalogoItem.empresa_id == eid, models.CatalogoItem.activo == True
    ).order_by(models.CatalogoItem.tipo, models.CatalogoItem.descripcion).all()
    return templates.TemplateResponse("catalogo.html", {"request": request, "user": user, "items": items, "empresa_vista": empresa_vista})


@app.get("/clientes", response_class=HTMLResponse)
def clientes_page(request: Request, db: Session = Depends(get_db)):
    user = _user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login")
    eid = get_effective_empresa_id(user, request)
    empresa_vista = db.query(models.Empresa).filter(models.Empresa.id == eid).first() if user.rol == "superadmin" else None
    lista = db.query(models.Cliente).filter(
        models.Cliente.empresa_id == eid, models.Cliente.activo == True
    ).order_by(models.Cliente.nombre).all()
    return templates.TemplateResponse("clientes.html", {"request": request, "user": user, "clientes": lista, "empresa_vista": empresa_vista})


@app.get("/presupuestos", response_class=HTMLResponse)
def presupuestos_page(request: Request, db: Session = Depends(get_db)):
    user = _user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login")
    eid = get_effective_empresa_id(user, request)
    empresa_vista = db.query(models.Empresa).filter(models.Empresa.id == eid).first() if user.rol == "superadmin" else None
    lista = db.query(models.Presupuesto).filter(
        models.Presupuesto.empresa_id == eid
    ).order_by(models.Presupuesto.created_at.desc()).all()
    clientes_lista = db.query(models.Cliente).filter(
        models.Cliente.empresa_id == eid, models.Cliente.activo == True
    ).order_by(models.Cliente.nombre).all()
    return templates.TemplateResponse("presupuestos.html", {
        "request": request, "user": user, "empresa_vista": empresa_vista,
        "presupuestos": lista, "clientes": clientes_lista
    })


@app.get("/presupuestos/{id}", response_class=HTMLResponse)
def presupuesto_detail(id: int, request: Request, db: Session = Depends(get_db)):
    user = _user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login")
    eid = get_effective_empresa_id(user, request)
    empresa_vista = db.query(models.Empresa).filter(models.Empresa.id == eid).first() if user.rol == "superadmin" else None
    p = db.query(models.Presupuesto).filter(
        models.Presupuesto.id == id, models.Presupuesto.empresa_id == eid
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    clientes_lista = db.query(models.Cliente).filter(
        models.Cliente.empresa_id == eid, models.Cliente.activo == True
    ).order_by(models.Cliente.nombre).all()
    return templates.TemplateResponse("presupuesto_detail.html", {
        "request": request, "user": user, "empresa_vista": empresa_vista,
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


@app.get("/configuracion", response_class=HTMLResponse)
def configuracion_page(request: Request, db: Session = Depends(get_db)):
    user = _user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login")
    if user.rol not in ("admin", "superadmin"):
        return RedirectResponse(url="/dashboard")
    eid     = get_effective_empresa_id(user, request)
    empresa = db.query(models.Empresa).filter(models.Empresa.id == eid).first()
    return templates.TemplateResponse("configuracion.html", {
        "request": request, "user": user, "empresa": empresa
    })

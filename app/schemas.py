from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime


# ── Auth ──────────────────────────────────────────────────────────────────────

class EmpresaCreate(BaseModel):
    nombre: str
    email: str
    telefono: Optional[str] = None
    nif: Optional[str] = None
    admin_nombre: str
    admin_email: str
    admin_password: str


class LoginForm(BaseModel):
    email: str
    password: str


# ── Usuarios ──────────────────────────────────────────────────────────────────

class UsuarioCreate(BaseModel):
    nombre: str
    email: str
    password: str
    rol: Literal["admin", "operario"] = "operario"


class UsuarioResponse(BaseModel):
    id: int
    nombre: str
    email: str
    rol: str
    activo: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── Catálogo ──────────────────────────────────────────────────────────────────

class CatalogoItemCreate(BaseModel):
    tipo: Literal["Material", "Mano de Obra", "Varios"]
    descripcion: str
    precio_unitario: float = 0.0
    unidad: str = "ud"
    referencia: Optional[str] = None
    marca: Optional[str] = None


class CatalogoItemResponse(BaseModel):
    id: int
    tipo: str
    descripcion: str
    precio_unitario: float
    unidad: str
    referencia: Optional[str]
    marca: Optional[str] = None
    foto: Optional[str] = None
    activo: bool

    class Config:
        from_attributes = True


# ── Clientes ──────────────────────────────────────────────────────────────────

class ClienteCreate(BaseModel):
    nombre: str
    email: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    nif: Optional[str] = None
    notas: Optional[str] = None


class ClienteResponse(BaseModel):
    id: int
    nombre: str
    email: Optional[str]
    telefono: Optional[str]
    direccion: Optional[str]
    nif: Optional[str]
    notas: Optional[str]
    activo: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── Presupuestos ──────────────────────────────────────────────────────────────

class LineaCreate(BaseModel):
    tipo: Literal["Material", "Mano de Obra", "Varios"]
    descripcion: str
    cantidad: float = 1.0
    precio_unitario: float = 0.0
    orden: int = 0


class LineaUpdate(BaseModel):
    tipo: Optional[Literal["Material", "Mano de Obra", "Varios"]] = None
    descripcion: Optional[str] = None
    cantidad: Optional[float] = None
    precio_unitario: Optional[float] = None


class LineaResponse(BaseModel):
    id: int
    tipo: str
    descripcion: str
    cantidad: float
    precio_unitario: float
    orden: int

    class Config:
        from_attributes = True


class PresupuestoCreate(BaseModel):
    cliente_id: Optional[int] = None
    titulo: str
    validez_dias: int = 15
    notas: Optional[str] = None
    descuento: float = 0.0
    iva: float = 21.0


class PresupuestoUpdate(BaseModel):
    cliente_id: Optional[int] = None
    titulo: Optional[str] = None
    estado: Optional[str] = None
    validez_dias: Optional[int] = None
    notas: Optional[str] = None
    descuento: Optional[float] = None
    iva: Optional[float] = None


class PresupuestoResponse(BaseModel):
    id: int
    numero: str
    titulo: str
    estado: str
    fecha: datetime
    validez_dias: int
    notas: Optional[str]
    descuento: float
    iva: float
    token_cliente: Optional[str] = None
    fecha_lectura: Optional[datetime] = None
    fecha_aceptacion: Optional[datetime] = None
    cliente: Optional[ClienteResponse]
    lineas: List[LineaResponse] = []

    class Config:
        from_attributes = True


# ── Asistente IA (original) ───────────────────────────────────────────────────

class LineaItem(BaseModel):
    tipo: Literal["Material", "Mano de Obra", "Varios"] = Field(
        ..., description="Categoría del ítem"
    )
    descripcion: str = Field(..., description="Detalle del material o servicio")
    cantidad: float = Field(..., description="Cantidad de unidades, metros u horas")
    precio_unitario: float = Field(..., description="Precio por unidad sin IVA")


class ListaLineasPresupuesto(BaseModel):
    items: List[LineaItem]


class PeticionAsistente(BaseModel):
    id_presupuesto: str = Field(..., description="ID del presupuesto")
    mensaje: str = Field(..., description="Lo que el usuario dicta o escribe")

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Empresa(Base):
    __tablename__ = "empresas"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, index=True)
    telefono = Column(String)
    direccion = Column(String)
    nif = Column(String)
    logo = Column(Text, nullable=True)
    color_corporativo = Column(String, nullable=True, default="#1E40AF")
    created_at = Column(DateTime, server_default=func.now())

    usuarios = relationship("Usuario", back_populates="empresa")
    catalogo = relationship("CatalogoItem", back_populates="empresa")
    clientes = relationship("Cliente", back_populates="empresa")
    presupuestos = relationship("Presupuesto", back_populates="empresa")


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    rol = Column(String, default="operario")  # admin | operario
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    empresa = relationship("Empresa", back_populates="usuarios")


class CatalogoItem(Base):
    __tablename__ = "catalogo"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    tipo = Column(String, nullable=False)  # Material | Mano de Obra | Varios
    descripcion = Column(String, nullable=False)
    precio_unitario = Column(Float, default=0.0)
    unidad = Column(String, default="ud")
    referencia = Column(String)
    marca = Column(String, nullable=True)
    foto = Column(String, nullable=True)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    empresa = relationship("Empresa", back_populates="catalogo")


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    nombre = Column(String, nullable=False)
    email = Column(String)
    telefono = Column(String)
    direccion = Column(String)
    nif = Column(String)
    notas = Column(Text)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    empresa = relationship("Empresa", back_populates="clientes")
    presupuestos = relationship("Presupuesto", back_populates="cliente")


class Presupuesto(Base):
    __tablename__ = "presupuestos"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    numero = Column(String, nullable=False)
    titulo = Column(String, nullable=False)
    estado = Column(String, default="borrador")  # borrador | enviado | aceptado | rechazado
    fecha = Column(DateTime, server_default=func.now())
    validez_dias = Column(Integer, default=15)
    notas = Column(Text)
    descuento = Column(Float, default=0.0)
    iva = Column(Float, default=21.0)
    creado_por = Column(Integer, ForeignKey("usuarios.id"))
    token_cliente = Column(String, unique=True, index=True, nullable=True)
    fecha_lectura = Column(DateTime, nullable=True)
    fecha_aceptacion = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    empresa = relationship("Empresa", back_populates="presupuestos")
    cliente = relationship("Cliente", back_populates="presupuestos")
    lineas = relationship("LineaPresupuesto", back_populates="presupuesto",
                          cascade="all, delete-orphan", order_by="LineaPresupuesto.orden")


class ResetToken(Base):
    __tablename__ = "reset_tokens"

    id         = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    token      = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    usado      = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    usuario = relationship("Usuario")


class LineaPresupuesto(Base):
    __tablename__ = "lineas_presupuesto"

    id = Column(Integer, primary_key=True, index=True)
    presupuesto_id = Column(Integer, ForeignKey("presupuestos.id"), nullable=False)
    tipo = Column(String, nullable=False)
    descripcion = Column(String, nullable=False)
    cantidad = Column(Float, default=1.0)
    precio_unitario = Column(Float, default=0.0)
    unidad = Column(String, default="ud", nullable=True)
    referencia = Column(String, nullable=True)
    orden = Column(Integer, default=0)

    presupuesto = relationship("Presupuesto", back_populates="lineas")

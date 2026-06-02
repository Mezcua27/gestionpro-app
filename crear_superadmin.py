"""
Crea el usuario superadmin para dar soporte a todas las empresas.
Ejecutar: python crear_superadmin.py
"""
from app.database import SessionLocal
from app import models
from app.auth import hash_password

db = SessionLocal()

# Crear empresa "Sistema" si no existe
empresa = db.query(models.Empresa).filter(models.Empresa.email == "soporte@gestionpro.sistema").first()
if not empresa:
    empresa = models.Empresa(
        nombre="GestiónPro Soporte",
        email="soporte@gestionpro.sistema",
        telefono="",
        nif="SISTEMA",
    )
    db.add(empresa)
    db.flush()
    print(f"Empresa de sistema creada (ID: {empresa.id})")
else:
    print(f"Empresa de sistema ya existe (ID: {empresa.id})")

# Pedir datos
print("\n--- Crear Superadmin ---")
nombre    = input("Nombre: ").strip() or "Soporte"
email     = input("Email: ").strip()
password  = input("Contraseña: ").strip()

if not email or not password:
    print("Error: email y contraseña son obligatorios")
    db.close()
    exit(1)

# Comprobar si ya existe
existente = db.query(models.Usuario).filter(models.Usuario.email == email).first()
if existente:
    print(f"Ya existe un usuario con ese email. Actualizando rol a superadmin...")
    existente.rol = "superadmin"
    existente.activo = True
    existente.password_hash = hash_password(password)
    db.commit()
    print(f"Usuario actualizado: {existente.nombre} ({existente.email})")
else:
    superadmin = models.Usuario(
        empresa_id=empresa.id,
        nombre=nombre,
        email=email,
        password_hash=hash_password(password),
        rol="superadmin",
        activo=True,
    )
    db.add(superadmin)
    db.commit()
    print(f"\nSuperadmin creado correctamente:")
    print(f"  Email:    {email}")
    print(f"  Nombre:   {nombre}")
    print(f"  Rol:      superadmin")

db.close()
print("\nYa puedes iniciar sesión en /login con estas credenciales.")

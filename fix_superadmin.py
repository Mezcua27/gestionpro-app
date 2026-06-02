from app.database import SessionLocal
from app import models

db = SessionLocal()
u = db.query(models.Usuario).filter(
    models.Usuario.email == "alejandromezcuamerino@gmail.com"
).first()

if u:
    u.rol = "superadmin"
    db.commit()
    print("OK:", u.nombre, "->", u.rol)
else:
    print("Usuario no encontrado")

db.close()


"""
Añade la columna `capitulo` a las tablas de líneas.
Uso: python migrar_capitulos.py
"""
from sqlalchemy import text
from app.database import SessionLocal

def migrar():
    db = SessionLocal()
    try:
        for tabla in ("lineas_presupuesto", "lineas_plantilla"):
            try:
                db.execute(text(f"ALTER TABLE {tabla} ADD COLUMN capitulo VARCHAR"))
                db.commit()
                print(f"✅ Columna añadida en {tabla}")
            except Exception as e:
                db.rollback()
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"ℹ️  {tabla}: columna ya existía, sin cambios.")
                else:
                    raise
        print("✅ Migración completada.")
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    migrar()
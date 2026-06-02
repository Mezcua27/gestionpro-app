"""
Busca y descarga fotos para cada producto del catálogo sin foto.
- Extrae la marca de la descripción si la columna marca está vacía
- Busca en DuckDuckGo Images: "{producto} {marca} producto"
- Descarga la imagen y la guarda en app/static/uploads/catalogo/
- Actualiza el campo foto en la base de datos
"""
import os
import re
import time
import uuid
import requests
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from app.database import SessionLocal
from app import models

UPLOAD_DIR = os.path.join("app", "static", "uploads", "catalogo")
os.makedirs(UPLOAD_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}
TIMEOUT = 10


def extraer_marca_de_descripcion(descripcion: str):
    """Si la descripción tiene ' — Marca' o ' - Marca' al final, extrae la marca."""
    for sep in [" — ", " - "]:
        if sep in descripcion:
            partes = descripcion.rsplit(sep, 1)
            if len(partes) == 2 and len(partes[1].strip()) < 40:
                return partes[0].strip(), partes[1].strip()
    return descripcion, ""


def buscar_imagen(query: str):
    """Busca una imagen en DuckDuckGo y devuelve la URL."""
    try:
        with DDGS() as ddgs:
            resultados = list(ddgs.images(
                query,
                max_results=5,
                safesearch="off",
                type_image="photo",
            ))
        for r in resultados:
            url = r.get("image", "")
            if url and url.startswith("http"):
                return url
    except Exception as e:
        print(f"  Error buscando '{query}': {e}")
    return None


def descargar_imagen(url: str, nombre_archivo: str):
    """Descarga la imagen y la guarda. Devuelve True si tuvo éxito."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True)
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type:
                return False
            ruta = os.path.join(UPLOAD_DIR, nombre_archivo)
            with open(ruta, "wb") as f:
                for chunk in resp.iter_content(1024 * 64):
                    f.write(chunk)
            size = os.path.getsize(ruta)
            if size < 2000:  # imagen demasiado pequeña, probablemente placeholder
                os.remove(ruta)
                return False
            return True
    except Exception as e:
        print(f"  Error descargando {url}: {e}")
    return False


def main():
    db = SessionLocal()
    try:
        items = db.query(models.CatalogoItem).filter(
            models.CatalogoItem.activo == True
        ).all()

        sin_foto = [i for i in items if not i.foto]
        print(f"Productos sin foto: {len(sin_foto)} de {len(items)} total\n")

        ok = 0
        fallo = 0

        for item in sin_foto:
            # 1. Extraer/limpiar descripción y marca
            if item.marca:
                descripcion_limpia = item.descripcion
                marca = item.marca
            else:
                descripcion_limpia, marca = extraer_marca_de_descripcion(item.descripcion)
                if marca:
                    item.descripcion = descripcion_limpia
                    item.marca = marca

            # Limpiar referencias entre paréntesis para la búsqueda
            desc_busqueda = re.sub(r'\([^)]+\)', '', descripcion_limpia).strip()
            query = f"{desc_busqueda} {marca} producto eléctrico".strip()

            print(f"[{item.id:3d}] {descripcion_limpia[:50]}")
            print(f"       Marca: {marca or '(sin marca)'}")
            print(f"       Buscando: {query[:70]}...")

            url = buscar_imagen(query)
            if not url:
                # Intentar sin "producto eléctrico"
                url = buscar_imagen(f"{desc_busqueda} {marca}")

            if url:
                ext = "jpg"
                if ".png" in url.lower():
                    ext = "png"
                elif ".webp" in url.lower():
                    ext = "webp"
                nombre = f"{item.empresa_id}_{item.id}_{uuid.uuid4().hex[:8]}.{ext}"
                if descargar_imagen(url, nombre):
                    item.foto = nombre
                    print(f"       OK Guardada: {nombre}")
                    ok += 1
                else:
                    print(f"       FALLO No se pudo descargar la imagen")
                    fallo += 1
            else:
                print(f"       FALLO No se encontro imagen")
                fallo += 1

            db.commit()
            time.sleep(1.5)  # pausa para no saturar DuckDuckGo
            print()

        print(f"\n{'='*50}")
        print(f"Completado: {ok} fotos descargadas, {fallo} fallos")

    finally:
        db.close()


if __name__ == "__main__":
    main()

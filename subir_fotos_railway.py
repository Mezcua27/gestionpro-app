"""
Busca y sube fotos de productos al catálogo de Railway vía API.
Uso: python subir_fotos_railway.py
"""
import re
import time
import uuid
import requests
from pathlib import Path

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

BASE_URL = "https://web-production-13f9c.up.railway.app"
EMAIL    = "alejandromezcuamerino@gmail.com"
PASSWORD = "Apocalipsi14."

HEADERS_BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}
TIMEOUT = 12
TMP_DIR = Path("tmp_fotos")
TMP_DIR.mkdir(exist_ok=True)


# ── Auth ──────────────────────────────────────────────────────────────────────

def login():
    r = requests.post(f"{BASE_URL}/auth/login",
                      json={"email": EMAIL, "password": PASSWORD},
                      timeout=15)
    r.raise_for_status()
    cookies = r.cookies
    print(f"Login OK — {r.json().get('nombre')} ({r.json().get('rol')})")
    return cookies


def entrar_empresa(cookies, empresa_id: int):
    r = requests.post(f"{BASE_URL}/api/superadmin/entrar/{empresa_id}",
                      cookies=cookies, timeout=10)
    r.raise_for_status()
    print(f"Entrando como empresa {empresa_id}: {r.json().get('empresa')}")
    # Fusionar cookies (view_empresa_id)
    cookies.update(r.cookies)
    return cookies


def get_empresas(cookies):
    r = requests.get(f"{BASE_URL}/api/superadmin/empresas", cookies=cookies, timeout=10)
    r.raise_for_status()
    return r.json()


def get_catalogo(cookies):
    r = requests.get(f"{BASE_URL}/api/catalogo/", cookies=cookies, timeout=15)
    r.raise_for_status()
    return r.json()


# ── Búsqueda de imagen ────────────────────────────────────────────────────────

def buscar_imagen(descripcion: str, marca: str) -> str | None:
    desc_limpia = re.sub(r'\([^)]+\)', '', descripcion).strip()
    query = f"{desc_limpia} {marca or ''} producto electrico".strip()
    try:
        with DDGS() as ddgs:
            resultados = list(ddgs.images(query, max_results=5,
                                          safesearch="off", type_image="photo"))
        for r in resultados:
            url = r.get("image", "")
            if url and url.startswith("http"):
                return url
    except Exception as e:
        print(f"  Error buscando '{query[:50]}': {e}")
    return None


def descargar_imagen(url: str, nombre: str) -> Path | None:
    try:
        r = requests.get(url, headers=HEADERS_BROWSER, timeout=TIMEOUT, stream=True)
        if r.status_code != 200 or "image" not in r.headers.get("content-type", ""):
            return None
        ruta = TMP_DIR / nombre
        with open(ruta, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
        if ruta.stat().st_size < 2000:
            ruta.unlink()
            return None
        return ruta
    except Exception as e:
        print(f"  Error descargando: {e}")
        return None


def subir_foto(cookies, item_id: int, ruta: Path) -> bool:
    try:
        with open(ruta, "rb") as f:
            r = requests.post(
                f"{BASE_URL}/api/catalogo/{item_id}/foto",
                cookies=cookies,
                files={"foto": (ruta.name, f, "image/jpeg")},
                timeout=30
            )
        if r.status_code == 200:
            return True
        print(f"  Error subiendo foto: {r.status_code} {r.text[:100]}")
        return False
    except Exception as e:
        print(f"  Error subiendo: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=== Subir fotos al catálogo de Railway ===\n")

    cookies = login()

    # Si es superadmin, preguntar en qué empresa entrar
    empresas = get_empresas(cookies)
    empresas_reales = [e for e in empresas if e["catalogo"] > 0]

    if not empresas_reales:
        print("No hay empresas con catálogo. Asegúrate de haber importado el catálogo primero.")
        return

    print("\nEmpresas con catálogo:")
    for e in empresas_reales:
        print(f"  [{e['id']}] {e['nombre']} — {e['catalogo']} productos")

    if len(empresas_reales) == 1:
        empresa_id = empresas_reales[0]["id"]
        print(f"\nUsando empresa: {empresas_reales[0]['nombre']}")
    else:
        empresa_id = int(input("\nIntroduce el ID de la empresa: ").strip())

    cookies = entrar_empresa(cookies, empresa_id)

    items = get_catalogo(cookies)
    sin_foto = [i for i in items if not i.get("foto")]
    print(f"\nProductos sin foto: {len(sin_foto)} de {len(items)}\n")

    if not sin_foto:
        print("Todos los productos ya tienen foto.")
        return

    ok = 0
    fallo = 0

    for item in sin_foto:
        desc  = item["descripcion"]
        marca = item.get("marca") or ""

        # Limpiar marca del final de la descripcion si viene incluida
        for sep in [" — ", " - "]:
            if sep in desc:
                partes = desc.rsplit(sep, 1)
                if len(partes[1].strip()) < 40:
                    desc  = partes[0].strip()
                    marca = marca or partes[1].strip()
                    break

        print(f"[{item['id']:3d}] {desc[:50]}")
        print(f"       Marca: {marca or '(sin marca)'}")

        url = buscar_imagen(desc, marca)
        if not url:
            print(f"       FALLO: no se encontro imagen\n")
            fallo += 1
            continue

        ext  = "png" if ".png" in url.lower() else ("webp" if ".webp" in url.lower() else "jpg")
        nombre = f"tmp_{item['id']}_{uuid.uuid4().hex[:6]}.{ext}"
        ruta = descargar_imagen(url, nombre)

        if not ruta:
            print(f"       FALLO: no se pudo descargar\n")
            fallo += 1
            continue

        if subir_foto(cookies, item["id"], ruta):
            print(f"       OK subida\n")
            ok += 1
        else:
            print(f"       FALLO al subir\n")
            fallo += 1

        ruta.unlink(missing_ok=True)
        time.sleep(1.5)

    print(f"\n{'='*45}")
    print(f"Completado: {ok} fotos subidas, {fallo} fallos")

    # Limpiar carpeta temporal
    import shutil
    shutil.rmtree(TMP_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()

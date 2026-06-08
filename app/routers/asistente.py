import os
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import anthropic
from app.database import get_db
from app import models, schemas
from app.auth import get_current_user

router = APIRouter()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _serializar_catalogo(items: list) -> str:
    """Convierte los items del catálogo en texto compacto para el prompt."""
    if not items:
        return "(catálogo vacío)"
    lineas = []
    for i in items[:200]:  # máximo 200 items para no saturar el contexto
        coste = f", coste: {i.precio_coste:.2f}€" if i.precio_coste else ""
        ref = f", ref: {i.referencia}" if i.referencia else ""
        marca = f", marca: {i.marca}" if i.marca else ""
        lineas.append(
            f"ID:{i.id} | {i.tipo} | {i.descripcion} | "
            f"{i.precio_unitario:.2f}€/{i.unidad}{coste}{ref}{marca}"
        )
    return "\n".join(lineas)


def _build_system_prompt_lineas(catalogo_txt: str) -> str:
    return f"""Eres un asistente experto en presupuestos de reformas y obras (fontanería, electricidad, albañilería, etc.).
Tu tarea es extraer de forma exacta la lista de materiales, mano de obra o servicios del mensaje del usuario.

CATÁLOGO DE LA EMPRESA (prioriza estos items cuando coincidan):
{catalogo_txt}

Responde ÚNICAMENTE con un JSON válido, sin texto adicional, sin bloques de código, sin explicaciones.
El JSON debe tener esta estructura exacta:
{{
  "items": [
    {{
      "tipo": "Material",
      "descripcion": "descripción del ítem",
      "cantidad": 1.0,
      "precio_unitario": 0.0,
      "precio_coste": 0.0,
      "catalogo_item_id": null
    }}
  ]
}}

Reglas:
- "tipo" solo puede ser: "Material", "Mano de Obra" o "Varios"
- "cantidad" y "precio_unitario" siempre son números decimales
- Si el ítem coincide con uno del catálogo, usa su precio_unitario exacto, su precio_coste exacto y pon su ID en "catalogo_item_id"
- Si no hay coincidencia en el catálogo, estima precio de mercado razonable en euros y pon "catalogo_item_id": null
- "precio_coste" es el coste real del material/servicio (sin margen). Si no lo sabes, usa 0.0
- Si el usuario no especifica cantidad, usa 1.0
- Nunca incluyas texto fuera del JSON"""


def _build_system_prompt_presupuesto(catalogo_txt: str) -> str:
    return f"""Eres un asistente experto en presupuestos de reformas y obras.
Tu tarea es generar un presupuesto completo a partir de la descripción del usuario.

CATÁLOGO DE LA EMPRESA (prioriza estos items cuando coincidan):
{catalogo_txt}

Responde ÚNICAMENTE con un JSON válido, sin texto adicional, sin bloques de código, sin explicaciones.
El JSON debe tener esta estructura exacta:
{{
  "titulo": "Título descriptivo del presupuesto",
  "lineas": [
    {{
      "tipo": "Material",
      "descripcion": "descripción del ítem",
      "cantidad": 1.0,
      "precio_unitario": 0.0,
      "precio_coste": 0.0,
      "catalogo_item_id": null
    }}
  ]
}}

Reglas:
- "titulo" debe ser un título corto y descriptivo del trabajo (máx 60 caracteres)
- "tipo" solo puede ser: "Material", "Mano de Obra" o "Varios"
- "cantidad" y "precio_unitario" siempre son números decimales
- Si el ítem coincide con uno del catálogo, usa su precio_unitario exacto, su precio_coste exacto y pon su ID en "catalogo_item_id"
- Si no hay coincidencia, estima precio de mercado razonable en euros
- "precio_coste" es el coste real sin margen. Si no lo sabes, usa 0.0
- Nunca incluyas texto fuera del JSON"""


def _limpiar_raw(raw: str) -> str:
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _normalizar_item(item: dict) -> dict:
    tipos_validos = {"Material", "Mano de Obra", "Varios"}
    tipo = item.get("tipo", "Material")
    if tipo not in tipos_validos:
        tipo = "Material"
    return {
        "tipo":             tipo,
        "descripcion":      str(item.get("descripcion", "")).strip(),
        "cantidad":         float(item.get("cantidad", 1.0)),
        "precio_unitario":  float(item.get("precio_unitario", 0.0)),
        "precio_coste":     float(item.get("precio_coste", 0.0)),
        "catalogo_item_id": item.get("catalogo_item_id"),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/procesar-lineas")
def procesar_lineas(
    peticion: schemas.PeticionAsistente,
    request: Request,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)

    presupuesto_id = int(peticion.id_presupuesto)
    p = db.query(models.Presupuesto).filter(
        models.Presupuesto.id == presupuesto_id,
        models.Presupuesto.empresa_id == user.empresa_id
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada.")

    # Cargar catálogo de la empresa
    catalogo = db.query(models.CatalogoItem).filter(
        models.CatalogoItem.empresa_id == user.empresa_id,
        models.CatalogoItem.activo == True
    ).order_by(models.CatalogoItem.tipo, models.CatalogoItem.descripcion).all()
    catalogo_txt = _serializar_catalogo(catalogo)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=_build_system_prompt_lineas(catalogo_txt),
            messages=[{"role": "user", "content": peticion.mensaje}]
        )

        data = json.loads(_limpiar_raw(message.content[0].text.strip()))
        items = [_normalizar_item(i) for i in data.get("items", [])]

        return {
            "status":          "procesado",
            "id_presupuesto":  peticion.id_presupuesto,
            "datos_extraidos": items,
        }

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Error procesando respuesta del asistente: {str(e)}")
    except anthropic.APIError as e:
        raise HTTPException(status_code=500, detail=f"Error API Anthropic: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generar-presupuesto")
def generar_presupuesto(
    data: dict,
    request: Request,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)

    mensaje = (data.get("mensaje") or "").strip()
    if not mensaje:
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada")

    # Cargar catálogo de la empresa
    catalogo = db.query(models.CatalogoItem).filter(
        models.CatalogoItem.empresa_id == user.empresa_id,
        models.CatalogoItem.activo == True
    ).order_by(models.CatalogoItem.tipo, models.CatalogoItem.descripcion).all()
    catalogo_txt = _serializar_catalogo(catalogo)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=_build_system_prompt_presupuesto(catalogo_txt),
            messages=[{"role": "user", "content": mensaje}]
        )

        data_parsed = json.loads(_limpiar_raw(message.content[0].text.strip()))
        titulo  = str(data_parsed.get("titulo", "Nuevo presupuesto")).strip()[:100]
        lineas  = [_normalizar_item(l) for l in data_parsed.get("lineas", [])]

        return {"titulo": titulo, "lineas": lineas}

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Error procesando respuesta: {str(e)}")
    except anthropic.APIError as e:
        raise HTTPException(status_code=500, detail=f"Error API Anthropic: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

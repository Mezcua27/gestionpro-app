import os
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import anthropic
from app.database import get_db
from app import models, schemas
from app.auth import get_current_user

router = APIRouter()

SYSTEM_PROMPT = """Eres un asistente experto en presupuestos de reformas y obras (fontanería, electricidad, albañilería, etc.).
Tu tarea es extraer de forma exacta la lista de materiales, mano de obra o servicios adicionales del mensaje del usuario.

Responde ÚNICAMENTE con un JSON válido, sin texto adicional, sin bloques de código, sin explicaciones.
El JSON debe tener esta estructura exacta:
{
  "items": [
    {
      "tipo": "Material",
      "descripcion": "descripción del ítem",
      "cantidad": 1.0,
      "precio_unitario": 0.0
    }
  ]
}

Reglas:
- "tipo" solo puede ser: "Material", "Mano de Obra" o "Varios"
- "cantidad" y "precio_unitario" siempre son números decimales
- Si el usuario no especifica precio, estima un precio de mercado razonable en euros o usa 0.0
- Si el usuario no especifica cantidad, usa 1.0
- Nunca incluyas texto fuera del JSON"""

SYSTEM_PROMPT_PRESUPUESTO = """Eres un asistente experto en presupuestos de reformas y obras.
Tu tarea es generar un presupuesto completo a partir de la descripción del usuario.

Responde ÚNICAMENTE con un JSON válido, sin texto adicional, sin bloques de código, sin explicaciones.
El JSON debe tener esta estructura exacta:
{
  "titulo": "Título descriptivo del presupuesto",
  "lineas": [
    {
      "tipo": "Material",
      "descripcion": "descripción del ítem",
      "cantidad": 1.0,
      "precio_unitario": 0.0
    }
  ]
}

Reglas:
- "titulo" debe ser un título corto y descriptivo del trabajo (máx 60 caracteres)
- "tipo" solo puede ser: "Material", "Mano de Obra" o "Varios"
- "cantidad" y "precio_unitario" siempre son números decimales
- Si el usuario no especifica precio, estima un precio de mercado razonable en euros
- Si el usuario no especifica cantidad, usa 1.0
- Nunca incluyas texto fuera del JSON"""


@router.post("/procesar-lineas")
def procesar_lineas(
    peticion: schemas.PeticionAsistente,
    request: Request,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)

    # Verificar que el presupuesto pertenece a la empresa del usuario
    presupuesto_id = int(peticion.id_presupuesto)
    p = db.query(models.Presupuesto).filter(
        models.Presupuesto.id == presupuesto_id,
        models.Presupuesto.empresa_id == user.empresa_id
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY no configurada. Añádela en las variables de Railway."
        )

    try:
        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": peticion.mensaje}
            ]
        )

        raw = message.content[0].text.strip()

        # Limpiar posibles bloques de código si el modelo los incluye
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        items_raw = data.get("items", [])

        # Validar y normalizar cada ítem
        tipos_validos = {"Material", "Mano de Obra", "Varios"}
        items = []
        for item in items_raw:
            tipo = item.get("tipo", "Material")
            if tipo not in tipos_validos:
                tipo = "Material"
            items.append({
                "tipo":            tipo,
                "descripcion":     str(item.get("descripcion", "")).strip(),
                "cantidad":        float(item.get("cantidad", 1.0)),
                "precio_unitario": float(item.get("precio_unitario", 0.0)),
            })

        return {
            "status":          "procesado",
            "id_presupuesto":  peticion.id_presupuesto,
            "datos_extraidos": items,
        }

    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error procesando respuesta del asistente: {str(e)}"
        )
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
    get_current_user(request, db)  # solo requiere autenticación

    mensaje = (data.get("mensaje") or "").strip()
    if not mensaje:
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada")

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=SYSTEM_PROMPT_PRESUPUESTO,
            messages=[{"role": "user", "content": mensaje}]
        )

        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data_parsed = json.loads(raw)
        titulo   = str(data_parsed.get("titulo", "Nuevo presupuesto")).strip()[:100]
        lineas   = data_parsed.get("lineas", [])

        tipos_validos = {"Material", "Mano de Obra", "Varios"}
        lineas_limpias = []
        for l in lineas:
            tipo = l.get("tipo", "Material")
            if tipo not in tipos_validos:
                tipo = "Material"
            lineas_limpias.append({
                "tipo":            tipo,
                "descripcion":     str(l.get("descripcion", "")).strip(),
                "cantidad":        float(l.get("cantidad", 1.0)),
                "precio_unitario": float(l.get("precio_unitario", 0.0)),
            })

        return {"titulo": titulo, "lineas": lineas_limpias}

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Error procesando respuesta: {str(e)}")
    except anthropic.APIError as e:
        raise HTTPException(status_code=500, detail=f"Error API Anthropic: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

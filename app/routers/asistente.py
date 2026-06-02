import os
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from openai import OpenAI
from app.database import get_db
from app import models, schemas
from app.auth import get_current_user

router = APIRouter()


@router.post("/procesar-lineas")
def procesar_lineas(peticion: schemas.PeticionAsistente, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Verificar que el presupuesto pertenece a la empresa del usuario
    presupuesto_id = int(peticion.id_presupuesto)
    p = db.query(models.Presupuesto).filter(
        models.Presupuesto.id == presupuesto_id,
        models.Presupuesto.empresa_id == user.empresa_id
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un asistente experto en presupuestos de reformas y obras (fontanería, electricidad, etc.). "
                        "Tu tarea es escuchar lo que pide el operario o gestor y extraer de forma exacta la lista de "
                        "materiales, mano de obra o servicios adicionales con sus respectivas cantidades y precios unitarios. "
                        "Si el usuario no especifica el precio de algo, intenta estimar un precio de mercado razonable o pon 0.0."
                    )
                },
                {"role": "user", "content": peticion.mensaje}
            ],
            response_format=schemas.ListaLineasPresupuesto,
        )
        lineas_extraidas = completion.choices[0].message.parsed
        return {
            "status": "procesado",
            "id_presupuesto": peticion.id_presupuesto,
            "datos_extraidos": lineas_extraidas.items
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

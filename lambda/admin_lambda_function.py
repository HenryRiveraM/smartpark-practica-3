"""Handler de OTRA Lambda, sin URL publica ni permiso de invocacion Alexa.

El campo JSON no autentica al operador: la frontera es IAM y una funcion separada.
"""
import logging

from administration.runtime import get_admin_service
from services.errors import UserError
from services.validation import validate_thing, validate_user


def lambda_handler(event, context):
    # No interpretar sobres Alexa ni permitir campos que cambien politica/TTL/intentos.
    if not isinstance(event, dict) or set(event) != {"allowedUserId", "thingName"}:
        return {"error": "Evento administrativo inválido. Se requieren únicamente allowedUserId y thingName."}
    try:
        user = validate_user(event["allowedUserId"])
        thing = validate_thing(event["thingName"])
        return get_admin_service().generate(user, thing)
    except UserError as exc:
        if type(exc) is not UserError:
            logging.getLogger("smartpark.admin").warning("generation_failed type=%s", type(exc).__name__)
        return {"error": str(exc)}
    except Exception:
        # Ni evento, excepcion, PIN, userId ni detalles de AWS en CloudWatch.
        logging.getLogger("smartpark.admin").warning("generation_failed type=UnexpectedError")
        return {"error": "No se pudo completar la generación. No reintentar automáticamente; comprueba si ya existe una ventana activa."}

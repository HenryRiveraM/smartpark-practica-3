"""Entrada Lambda ASK. Importar no crea clientes ni consulta AWS."""
from datetime import datetime, timezone
import os
import re

from ask_sdk_core.skill_builder import SkillBuilder

from handlers.barrier_handlers import AbrirBarreraHandler, CerrarBarreraHandler, EstadoBarreraHandler
from handlers.binding_handlers import CambiarVinculacionHandler, DesvincularParqueoHandler, VincularParqueoHandler
from handlers.sensor_handlers import ConsultarDistanciaHandler, ConsultarVehiculoHandler
from handlers.system_handlers import ExitHandler, FallbackHandler, HelpHandler, LaunchHandler, SafeExceptionHandler, SessionEndedHandler
from services.validation import validate_user
from services.errors import UserError

builder = SkillBuilder()
for handler in (
    LaunchHandler(), VincularParqueoHandler(), CambiarVinculacionHandler(), DesvincularParqueoHandler(),
    ConsultarDistanciaHandler(), ConsultarVehiculoHandler(), AbrirBarreraHandler(), CerrarBarreraHandler(),
    EstadoBarreraHandler(), HelpHandler(), ExitHandler(), SessionEndedHandler(), FallbackHandler(),
):
    builder.add_request_handler(handler)
builder.add_exception_handler(SafeExceptionHandler())
_sdk_handler = builder.lambda_handler()


def _safe_response(message):
    return {"version": "1.0", "response": {"outputSpeech": {"type": "PlainText", "text": message}, "shouldEndSession": True}}


def lambda_handler(event, context):
    # La autenticidad del origen depende ademas del trigger Alexa y su Skill ID.
    # Esta comprobacion evita llamadas AWS si falta configuracion o se cruza una skill.
    expected = os.environ.get("ALEXA_SKILL_ID", "")
    if not re.fullmatch(r"amzn1\.ask\.skill\.[A-Za-z0-9-]{1,128}", expected, re.ASCII):
        return _safe_response("La skill todavía no está configurada correctamente.")
    try:
        if not isinstance(event, dict) or event.get("version") != "1.0":
            raise ValueError("envelope")
        system = event["context"]["System"]
        if system["application"]["applicationId"] != expected:
            raise ValueError("skill")
        session = event.get("session", {})
        session_app = session.get("application", {}).get("applicationId")
        if session_app is not None and session_app != expected:
            raise ValueError("session skill")
        request = event["request"]
        if not isinstance(request.get("requestId"), str) or not request["requestId"]:
            raise ValueError("request id")
        timestamp = datetime.fromisoformat(request["timestamp"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("timezone")
        age = (datetime.now(timezone.utc)-timestamp).total_seconds()
        if age < -30 or age > 150:
            raise ValueError("request age")
        if request.get("type") != "SessionEndedRequest":
            user = validate_user(system["user"]["userId"])
            session_user = session.get("user", {}).get("userId")
            if session_user is not None and session_user != user:
                raise ValueError("session user")
        return _sdk_handler(event, context)
    except UserError as exc:
        return _safe_response(str(exc))
    except (KeyError, TypeError, ValueError, AttributeError):
        return _safe_response("No pude validar la solicitud de Alexa. Abre la skill de nuevo.")
    except Exception:
        # La deserializacion del SDK puede fallar antes del manejador de excepciones.
        return _safe_response("No pude procesar la solicitud. Intenta de nuevo más tarde.")

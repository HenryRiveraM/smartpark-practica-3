import math

from .common import IntentHandler, bound_device, say
from services.errors import UserError


class ConsultarDistanciaHandler(IntentHandler):
    intent_name = "ConsultarDistanciaIntent"

    def handle(self, handler_input):
        shadow, thing = bound_device(handler_input)
        distance = shadow.get_reported(thing, "distancia_cm")
        if type(distance) not in (int, float) or not math.isfinite(distance) or not 2 <= distance <= 400:
            raise UserError("La distancia reportada es desconocida o está fuera del rango válido del sensor.")
        text = f"{distance:.1f}".rstrip("0").rstrip(".").replace(".", ",")
        return say(handler_input, f"La última distancia reportada es de {text} centímetros.", keep_open=True)


class ConsultarVehiculoHandler(IntentHandler):
    intent_name = "ConsultarVehiculoIntent"

    def handle(self, handler_input):
        shadow, thing = bound_device(handler_input)
        value = shadow.get_reported(thing, "vehiculo_detectado")
        if type(value) is not bool:
            raise UserError("La presencia de vehículo es desconocida. No tengo una medición válida.")
        return say(
            handler_input,
            "El último reporte indica que hay un vehículo esperando." if value else "El último reporte indica que no hay un vehículo esperando.",
            keep_open=True,
        )

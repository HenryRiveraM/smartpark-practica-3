from .common import IntentHandler, bound_device, say
from services.errors import UserError


class AbrirBarreraHandler(IntentHandler):
    intent_name = "AbrirBarreraIntent"
    target = "abierta"
    action = "abrir"

    def handle(self, handler_input):
        shadow, thing = bound_device(handler_input)
        shadow.set_barrier(thing, self.target)
        return say(
            handler_input,
            f"Solicité {self.action} la barrera. Puedes consultar su estado para conocer el último reporte del dispositivo.",
            keep_open=True,
            reprompt="Puedes decir consultar estado, consultar distancia o salir.",
        )


class CerrarBarreraHandler(AbrirBarreraHandler):
    intent_name = "CerrarBarreraIntent"
    target = "cerrada"
    action = "cerrar"


class EstadoBarreraHandler(IntentHandler):
    intent_name = "EstadoBarreraIntent"

    def handle(self, handler_input):
        shadow, thing = bound_device(handler_input)
        value = shadow.get_reported(thing, "barrera")
        if not isinstance(value, str) or value not in {"abierta", "cerrada"}:
            raise UserError("El dispositivo no ha informado un estado de barrera reconocido.")
        return say(handler_input, f"Según el último estado reportado, la barrera está {value}.", keep_open=True)

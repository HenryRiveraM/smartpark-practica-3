import logging

from ask_sdk_core.dispatch_components import AbstractExceptionHandler, AbstractRequestHandler
from ask_sdk_core.utils import is_intent_name, is_request_type

from .common import get_backend, say, user_id
from services.errors import UserError

HELP = "Dentro de SmartPark puedes decir abrir, cerrar, consultar estado, consultar distancia o consultar vehículo. Para terminar, di salir o cancelar. También puedes vincular tu parqueo con un código autorizado, cambiar la vinculación o desvincularlo."


class LaunchHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        binding = get_backend().bindings.get_binding(user_id(handler_input))
        text = "Bienvenido a parqueo inteligente. "
        if binding:
            text += "Puedes decir abrir, consultar estado, cerrar o salir."
        else:
            text += "Primero pide un código al administrador y di: vincula mi parqueo con el código, seguido de los cuatro dígitos."
        return say(handler_input, text, keep_open=True)


class HelpHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        return say(handler_input, HELP, keep_open=True)


class ExitHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return any(is_intent_name(name)(handler_input) for name in ("AMAZON.CancelIntent", "AMAZON.StopIntent"))

    def handle(self, handler_input):
        return say(handler_input, "Hasta luego.")


class SessionEndedHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        return handler_input.response_builder.response


class FallbackHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return True

    def handle(self, handler_input):
        return say(handler_input, "No reconocí esa solicitud. Di abrir, cerrar, consultar estado, consultar distancia o consultar vehículo. Para terminar, di salir. También puedes pedir ayuda.", keep_open=True)


class SafeExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        # No eventos, slots, userId, nombres de Things, codigos ni mensajes de AWS.
        if type(exception) is not UserError:
            logging.getLogger("smartpark").warning("request_failed type=%s", type(exception).__name__)
        message = str(exception) if isinstance(exception, UserError) else "No pude completar la solicitud. Intenta de nuevo más tarde."
        return say(handler_input, message)

from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.utils import is_intent_name

from services.errors import UserError
from services.runtime import get_backend
from services.validation import validate_user


def user_id(handler_input):
    return validate_user(handler_input.request_envelope.context.system.user.user_id)


def bound_device(handler_input):
    backend = get_backend()
    binding = backend.bindings.get_binding(user_id(handler_input))
    if binding is None:
        raise UserError("No tienes un parqueo vinculado. Pide un código al administrador y di: vincula mi parqueo con el código, seguido de los cuatro dígitos.")
    return backend.shadow, binding.thing_name


SESSION_REPROMPT = "Puedes decir abrir, cerrar, consultar estado, consultar distancia, consultar vehículo o salir."


def say(handler_input, text, *, keep_open=False, reprompt=SESSION_REPROMPT):
    builder = handler_input.response_builder.speak(text)
    if keep_open:
        return builder.ask(reprompt).set_should_end_session(False).response
    return builder.set_should_end_session(True).response


class IntentHandler(AbstractRequestHandler):
    intent_name = ""

    def can_handle(self, handler_input):
        return is_intent_name(self.intent_name)(handler_input)

from .common import IntentHandler, get_backend, say, user_id
from services.errors import UserError
from services.validation import pairing_key


class VincularParqueoHandler(IntentHandler):
    intent_name = "VincularParqueoIntent"
    replacing = False

    def handle(self, handler_input):
        user = user_id(handler_input)
        slots = handler_input.request_envelope.request.intent.slots or {}
        code_slot = slots.get("codigo")
        code = code_slot.value if code_slot else None
        pairing_key(code)  # Rechazar slots invalidos antes de cualquier llamada AWS.
        backend = get_backend()
        previous = backend.bindings.get_binding(user)
        if previous is not None and not self.replacing:
            raise UserError("Ya tienes un parqueo vinculado. Para reemplazarlo di: cambia mi vinculación con el código, seguido del nuevo código.")
        if previous is None and self.replacing:
            raise UserError("Todavía no tienes una vinculación. Di: vincula mi parqueo con el código, seguido de tu código.")
        authorization = backend.bindings.authorize_code(user, code)
        backend.shadow.describe_thing(authorization[1])
        backend.bindings.save_binding(user, authorization, previous)
        if previous and previous.thing_name == authorization[1]:
            return say(handler_input, "Ese parqueo ya está vinculado a tu usuario. El código fue consumido.")
        return say(handler_input, "Tu parqueo quedó vinculado. Ya puedes consultar sus datos o solicitar abrir y cerrar la barrera.")


class CambiarVinculacionHandler(VincularParqueoHandler):
    intent_name = "CambiarVinculacionIntent"
    replacing = True


class DesvincularParqueoHandler(IntentHandler):
    intent_name = "DesvincularParqueoIntent"

    def handle(self, handler_input):
        deleted = get_backend().bindings.delete_binding(user_id(handler_input))
        return say(handler_input, "Desvinculé tu parqueo." if deleted else "No tienes un parqueo vinculado.")

"""Solo mensajes constantes aptos para voz; nunca exponer errores de AWS."""


class UserError(Exception):
    """Error que puede explicarse de forma segura al usuario."""


class ServiceError(UserError):
    def __init__(self):
        super().__init__(
            "No pude comunicarme con el servicio. Intenta de nuevo más tarde. "
            "Si solicitaste mover la barrera, consulta su estado antes de repetir la orden."
        )


class ConfigurationError(UserError):
    def __init__(self):
        super().__init__("La skill todavía no está configurada correctamente.")

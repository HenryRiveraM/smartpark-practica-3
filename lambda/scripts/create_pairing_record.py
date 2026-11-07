"""Operacion antigua deshabilitada: no crear PIN cortos sin ventana de intentos."""
if __name__ == "__main__":
    raise SystemExit(
        "Utiliza la Lambda administrativa SmartParkPairingAdmin y su handler "
        "admin_lambda_function.lambda_handler. No se generan registros manuales ni PIN sin proteccion."
    )

# Validación de fase 2

## Preparación del banco

1. Revisar fuente del servo, tierra común y adaptación ECHO a 3,3 V. Probar sin varilla/carga.
2. Revisar `config.h` y `secrets.h` locales. Confirmar endpoint, certificado activo, clave correspondiente y Amazon Root CA 1. No usar otro cliente con el mismo clientId del ESP32.
3. Revisar `aws-iot-policy.example.json` con el ID real de cuenta. Autorizar Connect para el clientId, Publish para get/update, Subscribe con topicfilter y Receive con topic para los cinco temas. Asociar certificado/política al Thing. No requiere Lambda, reglas ni otros servicios.
4. Compilar, cargar y abrir Serial a 115200. Guardar STATUS antes y después. Evitar reinicios repetidos: cada conexión requiere GET y consume presupuesto.
5. En AWS IoT Core de `us-east-1`, usar el cliente de prueba MQTT durante la prueba; cerrar suscripciones al terminar. Suscribirse solo a `$aws/things/smartpark-grupo9-01/shadow/update/accepted` y, si hace falta, a `update/rejected` y `update/delta` completos. Las suscripciones del cliente de prueba también pueden generar entregas adicionales.

## Apertura y cierre

Publicar en `$aws/things/smartpark-grupo9-01/shadow/update`:

```json
{"state":{"desired":{"barrera":"abierta"}}}
```

Esperar `AWS comando recibido: abierta`, movimiento físico y el UPDATE del ESP32 después del tiempo estimado. El primer accepted que se observa puede pertenecer a la propia orden de consola: comprobar el `clientToken` y `state.reported.barrera` del ESP32, además del servo físico. Repetir con:

```json
{"state":{"desired":{"barrera":"cerrada"}}}
```

También puede editarse `state.desired.barrera` en el Shadow clásico del Thing. No editar `reported` para simular confirmaciones. El firmware escribe solo `reported`, como recomienda el [modelo de documentos Shadow](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-document.html).

`desired` persiste en AWS. Si una orden Serial contradice ese valor, un delta posterior puede volver a aplicarlo. Para pruebas puramente Serial, retirar solamente `desired.barrera` desde la consola (`{"state":{"desired":{"barrera":null}}}`) o probar sin AWS. No borrar el Shadow ni la NVS como mecanismo de reinicio de presupuesto.

## Matriz de aceptación

Todas las verificaciones AWS/hardware de esta tabla están **pendientes**. Los PASS host validan lógica con dobles y JSON real; no validan la red, NVS real, TLS ni el circuito.

| # | Validación de banco | Resultado esperado | Cobertura host |
|---|---|---|---|
| 1 | Arrancar con Wi-Fi/certificados válidos | Hora NTP válida y MQTT/TLS conectado, sin revelar secretos | Estado de conexión simulado; TLS pendiente |
| 2 | Observar conexión y varios ciclos | GET aumenta una sola vez por conexión, no por lectura | PASS |
| 3 | Enviar desired abierta | Servo abre una vez y Serial registra orden | Cola AWS y servo doble: PASS |
| 4 | Enviar desired cerrada | Servo cierra, sin apertura por sensor | Lógica: PASS; hardware pendiente |
| 5 | Observar reported y accepted del ESP32 | Confirma tras fin estimado; no confundir accepted de consola | Espera, correlación y reported: PASS |
| 6 | Cambiar distancia ≥10 cm, sin cambiar presencia | UPDATE ordinario con distancia, respetando 10 s | PASS |
| 7 | Mantener objeto <15 cm por 3 muestras; retirarlo >18 cm | Cambia presencia estable, sin esperar intervalo ordinario; no abre solo | Debounce, histéresis y presencia: PASS |
| 8 | Mantener distancia estable, variarla <10 cm; repetir desired | Sin UPDATE extra antes de 30 s; respaldo agrupa cambios | PASS |
| 9 | Cortar Wi-Fi y restaurarlo | Reintentos espaciados, backoff, límite y Serial operativo | Backoff/límite: PASS; radio pendiente |
| 10 | Sin ESP32 conectado, cambiar desired; volver a conectarlo | Un GET recupera y ejecuta la última orden pendiente | GET con desired pendiente: PASS |
| 11 | Comparar STATUS antes/después; reiniciar sin borrar flash | Aumenta categoría correcta, cuota no se repone el mismo día | Registro NVS doble/restauración: PASS |
| 12 | Con configuración de banco, límite=8 y reserva=3, agotar ordinarias y controles | Ordinarias se detienen al total 5; control y recuperación hasta 8; servo local sigue | Límites/reserva/fallo NVS/servo: PASS |
| 13 | Para acelerar, configurar demo=60000; mantener conectividad y reconectar antes del fin | Desconexión tras tiempo acumulado, sin reconexión automática | Tiempo acumulado y bloqueo: PASS |
| 14 | Arrancar sin Wi-Fi o con demo vencida; OPEN/CLOSE/STATUS | Sensor cada 500 ms y servo/Serial operativos | Loop local y servo/parser: PASS |

En #12 no bajar el límite sobre un historial existente: un registro con consumo mayor que el nuevo techo se bloquea deliberadamente. Usar una placa de prueba sin historial para la configuración reducida, o ejecutar las pruebas host sin gastar AWS; no borrar la cuota de una placa para eludirla. Restaurar valores de demostración antes de la entrega. Un cambio de día UTC válido permite el siguiente presupuesto normalmente.

Pruebas complementarias pendientes: CA incorrecta debe impedir TLS; clave/certificado inválidos no deben conectarse; JSON inválido no debe mover el servo; rechazo UPDATE no debe provocar una tormenta de reintentos; corte de alimentación después de reservar una solicitud debe conservar o sobrecontar la reserva, nunca devolverla; sin NTP no debe publicar. Estas pruebas consumen intentos: realizar una secuencia corta y revisar STATUS.

## Ejecución real en desarrollo

- `pio run` sobre `espressif32@7.1.0`, ESP32Servo 1.1.2, PubSubClient 2.8.0 y ArduinoJson 6.21.5: SUCCESS.
- Uso final: RAM 46.924 / 327.680 bytes (14,3 %); flash 938.837 / 1.310.720 bytes (71,6 %). El uso de RAM informado por PlatformIO es estático; TLS, colas, JSON y la pila de tarea también consumen memoria dinámica que debe observarse en banco.
- `sh test/run_host_tests.sh`: compila C++17 con `-Wall -Wextra -Werror -pedantic`; PASS para sensor/servo/parser/loop local y gestor AWS con dobles.
- No se realizaron carga, conexión TLS real, órdenes en AWS, movimientos físicos ni comprobación de Billing.
- El primer intento de compilación quedó bloqueado por permisos de caché global; se repitió con permisos concedidos y terminó correctamente.

El binario contiene credenciales por diseño X.509 del dispositivo. `.pio/` es un artefacto local ignorado: no compartirlo ni subirlo a GitHub. Las plantillas públicas no contienen credenciales.

Verificación local de esta revisión (2026-11-08): ambas suites C++ PASS; 91 pruebas Lambda con dobles PASS (`.venv/bin/python -B -m unittest discover -s tests`, desde `lambda/`). El SDK ASK emite SyntaxWarning de escapes en Python 3.13; no hubo fallos. `git diff --check` sin errores. Sin llamadas AWS, carga al ESP32, commits ni pushes.

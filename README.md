# Práctica 3 — Integración de Objetos Inteligentes con Alexa y AWS IoT Core
 
**Asignatura:** Internet de las Cosas [SIS-234]
 
**Semestre:** 2-2026
 
**Grupo:** 9
 
**Integrantes:**
 
- Carlos Eduardo Iriarte Rodriguez
- Isabella Catherine Montes Iñiguez
- Henry Alejandro Rivera Mendez
---
 
**Informe técnico:** [docs/informe.md](docs/informe.md)
 
---
 
# SmartPark — fase 2

Firmware ESP32 DOIT DEVKIT V1, HC-SR04 y SG90 con control Serial y AWS IoT Core mediante Shadow clásico. Thing `smartpark-grupo9-01`, región `us-east-1`, MQTT/TLS 8883. No se añadieron otros servicios AWS ni apertura automática.

## Hardware y conexiones

| Componente | Conexión |
|---|---|
| HC-SR04 VCC | 5 V |
| HC-SR04 GND | Tierra común |
| HC-SR04 TRIG | GPIO 32 |
| HC-SR04 ECHO | GPIO 35 mediante adaptación a 3,3 V |
| SG90 señal | GPIO 18 |
| SG90 alimentación | Fuente externa regulada de 5 V |
| SG90 GND | Tierra de la fuente y GND del ESP32 |

No conectar ECHO de 5 V directamente al ESP32. Usar un adaptador de nivel o divisor resistivo: ECHO → 1 kΩ → GPIO 35 → 2 kΩ → GND (aproximadamente 3,33 V). Verificar el nivel real y tolerancias antes de conectar. GPIO 35 es solo entrada y no tiene resistencias pull-up/pull-down internas.

No alimentar el servo desde 3,3 V ni desde un GPIO. Dimensionar la fuente para los picos del servo y mantener tierra común; evitar unir salidas de fuentes distintas o realimentar USB. Primero probar el servo sin varilla ni carga; calibrar para evitar topes, bloqueo y sobrecorriente. El programa no detecta obstáculos ni confirma posición: es una prueba de banco, no un controlador de seguridad para una barrera real.

## Configuración y compilación

Se revisó y conservó la configuración local existente. Los valores de Wi-Fi se trasladaron de `config.h` a `secrets.h`, sin cambiar sus valores ni los PEM. Ambos archivos locales permanecen ignorados por Git.

Para una copia nueva, copiar `include/config.example.h` a `include/config.h` y `include/secrets.example.h` a `include/secrets.h`; completar Wi-Fi y los tres PEM. Nunca reemplazar archivos locales ya configurados con las plantillas.

```sh
pio run
sh test/run_host_tests.sh
# Solo con ESP32 conectado y cableado revisado:
pio run -t upload
pio device monitor
```

Las pruebas host requieren C++17 y ArduinoJson descargado por la compilación de PlatformIO. No necesitan el dispositivo, credenciales reales ni acceso a AWS. El script usa dobles para red, NVS, RTOS y hardware; el parser JSON y las clases del firmware son reales.

## Componentes y ahorro

- `UltrasonicSensor` y `BarrierServo` se preservan. `SerialCommands` conserva OPEN, CLOSE, STATUS, DISTANCE, HELP. Al arrancar se ordena cerrar, como en fase 1.
- `AwsIoTManager` gestiona Wi-Fi, NTP, X.509, MQTT, suscripciones, comandos, confirmaciones, cuota y demo en una tarea FreeRTOS. Colas de una posición intercambian la última muestra y el último comando, sin backlog de lecturas/comandos obsoletos. Solo `loop()` toca el hardware. TLS/DNS/MQTT pueden esperar en su tarea, sin bloquear Serial; el sensor conserva su espera acotada de hasta 30 ms por lectura.
- Cada 500 ms hay medida y salida Serial local. La histéresis original se conserva y AWS exige 3 muestras consecutivas para estabilizar presencia. Las variaciones de distancia inferiores a 10 cm respecto al último estado confirmado no disparan envíos.
- Respaldo de 30 s desde el último UPDATE intentado. Los cambios relevantes se envían al estar conectados y sincronizados, con separación ordinaria mínima de 10 s desde la última solicitud. No hay heartbeat de aplicación, publicaciones vacías, cola histórica ni envío de cada lectura. MQTT conserva su PING de protocolo con keepalive de 120 s.
- La presencia confirmada tiene prioridad sobre distancia y respaldo, y no espera el intervalo ordinario de 10 s. Usa cuota ordinaria, sin consumir reserva.
- Los cambios de barrera tienen prioridad y no esperan los 10 s ordinarios; esperan los 700 ms estimados por `BarrierServo`. Una confirmación de cambio ejecutado desplaza un informe pendiente con estado anterior; su reserva no se devuelve y su acuse tardío se ignora. No existe sensor que confirme la posición física. Se confirma únicamente la última posición estimada; órdenes opuestas intermedias se consolidan.
- Solo se publica `state.reported`: barrera, distancia, presencia y `barrera_posicion_estimada: true`. Datos inválidos se envían como `null` para eliminar datos viejos del Shadow, no como cero o ausencia falsa. La presencia desconocida también se elimina.
- Solo cinco suscripciones exactas: delta, GET accepted/rejected, UPDATE accepted/rejected. No se suscribe a `update/documents` ni a comodines. GET se solicita una vez tras conectar y enviar suscripciones; únicamente se repite en una nueva conexión/resincronización tras fallo. La semántica de temas está descrita en [AWS Device Shadow MQTT](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-mqtt.html).
- `clientToken` correlaciona respuestas propias y `version` descarta comandos atrasados. El estado confirmado avanza con UPDATE accepted, no al escribir TCP. PubSubClient publica QoS 0; el acuse de aplicación y el presupuesto cubren la incertidumbre, no garantizan entrega física.

Todos los valores ajustables están en `config.h`; la plantilla pública contiene los valores iniciales solicitados. `AWS_DEMO_MAX_CONNECTED_MS=0` desactiva el límite de demo.

## Presupuesto persistente

`ShadowBudget` cuenta cuatro categorías diarias UTC: periódicas, sensor, control y recuperación GET. El techo conservador de **1.000 incluye GET y UPDATE intentados**. Hasta 800 solicitudes totales se permiten informes ordinarios; desde ahí solo control y recuperación GET, hasta 1.000. Así se reservan 200 solicitudes para control y recuperación. También consumen reserva la sincronización inicial de barrera y las confirmaciones de cambios Serial. Un comando ya confirmado no consume otra solicitud.

Cada reserva se escribe en un registro NVS antes de llamar a MQTT. Un fallo de envío, rechazo o respuesta perdida no devuelve cuota: el contador es una cota conservadora de intentos, no una medición de operaciones facturadas. La suma de periódicas+sensor+control es UPDATE; sumando GET se obtienen solicitudes totales.

El registro guarda día UTC y categorías. Solo NTP con epoch válido habilita el presupuesto. El siguiente día UTC repone cuota mediante escritura persistente; un reinicio en el mismo día conserva el gasto. Retrocesos del reloj, registro corrupto y fallos NVS bloquean envíos. No hay comando de borrado de cuota. No borrar NVS ni usar `erase_flash` para repetir pruebas: eliminaría el historial local. Esta protección no resiste borrado externo ni manipulación de reloj/flash.

Con presupuesto ordinario agotado, una conexión existente sigue recibiendo comandos y usando la reserva. Si se desconecta, puede usar la reserva para el GET de resincronización. Al llegar al techo total, el servo y Serial siguen activos, aunque no se pueda confirmar en AWS. NTP fallido impide TLS y las publicaciones; el control local sigue disponible.

`STATUS` separa NVS, hora UTC, presupuesto de recuperación, estado MQTT, intentos y backoff restante. `STATUS` y el informe de 30 s muestran conectividad, último comando, categorías, UPDATE total, solicitudes totales, accepted/rejected de la sesión, reconexiones, omisiones, edad del último intento, día del presupuesto y estado de demo. Las lecturas imprimen distancia/presencia; STATUS añade barrera y movimiento estimado. “Omitidas” cuenta muestras sin cambios y decisiones pendientes bloqueadas por intervalo/cuota (estas últimas como máximo una vez por segundo); no representa ahorro monetario exacto. Accepted/rejected, omisiones y reconexiones son diagnósticos de sesión; solo los contadores de presupuesto persisten.

## Recuperación y duración de pruebas

No hay bucles de reconexión que esperen conectividad. Backoff exponencial desde 5 s, jitter y techo de 5 minutos; máximo configurable de 10 intentos consecutivos, compartidos entre Wi-Fi/MQTT y pérdidas de conexión. Un GET válido (incluido 404) reinicia ese contador; conectar sin sincronizar no lo reinicia. Tras agotar intentos, reiniciar expresamente para otra prueba; la cuota NVS se conserva.

GET sin respuesta tras 15 s provoca desconexión y recuperación con backoff. UPDATE sin respuesta permite hasta 3 intentos, contando cada uno; luego suspende informes. Un rechazo UPDATE o GET distinto de 404 suspende informes hasta reconectar: revisar política, documento y tamaño antes de reiniciar. GET 404 permite crear el Shadow con el primer reporte. El buffer MQTT inicial es 1024 bytes: un Shadow grande puede exigir aumentarlo y recompilar. PubSubClient no expone validación individual de SUBACK; permisos o suscripciones fallidas se evidencian por falta de respuestas y el límite de intentos.

La demo suma tiempo MQTT conectado durante el arranque, incluso entre reconexiones. A los 60 minutos envía DISCONNECT, apaga Wi-Fi y prohíbe reconectar hasta reiniciar. La cuota diaria no se repone al reiniciar. Una negociación o lectura de socket en curso puede retrasar unos segundos la evaluación del vencimiento; TLS tiene timeout de handshake de 5 s y socket MQTT de 2 s. No es una desconexión en tiempo real estricto.

## Prueba desde AWS

Ver el procedimiento y la matriz de 14 validaciones en [docs/PRUEBAS_AWS.md](docs/PRUEBAS_AWS.md). Se incluye [política de ejemplo](docs/aws-iot-policy.example.json) para revisión; reemplazar el ID de cuenta y asociarla al certificado activo y al Thing. No se aplicó ninguna política ni se modificó la cuenta AWS desde esta sesión.

## Consumo y AWS Billing

En una demo estable de 60 minutos se esperan aproximadamente 1 GET, 1 sincronización inicial y 119–120 respaldos, más cambios y reintentos. Es una estimación del firmware, no una medición AWS. Mantener conectado todo el día produciría 2880 respaldos sin cuota: por eso se limita la sesión y se suspenden envíos al gastar el presupuesto.

Comparar STATUS antes/después de cada prueba. AWS también mide conectividad, mensajería y operaciones Shadow; el contador local no incluye comandos de consola, otras aplicaciones, respuestas, entregas adicionales ni otros dispositivos. Verificar en Billing/Cost Explorer y Free Tier/Créditos: elegibilidad y vencimiento de la cuenta, saldo, consumo agregado, región, tamaño de documentos/mensajes y actividad externa. Las condiciones cambian según el plan y fecha de alta. Revisar la [tarifa oficial de IoT Core](https://aws.amazon.com/iot-core/pricing/). **1.000 solicitudes locales no garantizan gasto cero ni un techo absoluto de factura.** No se habilitaron reglas, logs cloud ni servicios adicionales.

## Resultado de verificación

Compilación PlatformIO ESP32: SUCCESS. Pruebas host: PASS (lógica con dobles; no pruebas físicas). Ver detalles finales de uso de memoria y alcance en `docs/PRUEBAS_AWS.md`.

No se cargó firmware, no se conectó el dispositivo a AWS y no se comprobó Billing. La aceptación TLS real, certificados/política, apertura/cierre físico, precisión del sensor, persistencia ante corte eléctrico y tiempos reales siguen pendientes de banco.

No se realizaron commits ni pushes. `config.h`, `secrets.h`, `.pio/` y `.vscode/` están ignorados; un archivo ya rastreado no deja de estarlo por `.gitignore`. Antes de una publicación autorizada, revisar el índice, incluido `.vscode/extensions.json` heredado de fase 1, y excluir toda configuración local del editor.

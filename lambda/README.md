# SmartPark — Alexa y vinculación temporal con PIN de cuatro dígitos

Se conserva el backend modular existente de Alexa, Python 3.13, la tabla `SmartParkBindings` con clave String `userId` y el Shadow clásico. No se modificó firmware ni se desplegaron recursos. La generación se prepara para **otra Lambda**, `SmartParkPairingAdmin`, invocada manualmente por un operador IAM autorizado.

## Archivos y responsabilidades

| Archivo / carpeta | Función |
|---|---|
| `lambda_function.py`, `handlers/` | Entrada pública Alexa e intents existentes; no generan PIN |
| `services/validation.py` | `pairing_key()`: cuatro dígitos ASCII entre 1000 y 9999, espacios/tabs opcionales, SHA-256 |
| `services/pairing_policy.py` | Política fija: 300 s, 3 intentos, máximo 3 candidatos por colisión; clave de ventana por usuario |
| `services/dynamodb_service.py` | `authorize_code()`, `save_binding()`, vinculaciones y consumo condicional |
| `services/runtime.py`, `shadow_service.py` | Clientes reutilizados y Shadow; consultas/órdenes conservadas |
| `admin_lambda_function.py` | Handler administrativo independiente, nunca incluido en el ZIP de Alexa |
| `administration/pairing_service.py`, `runtime.py` | Generación criptográfica, DescribeThing y registro transaccional automático |
| `scripts/build.sh`, `verify_package.py` | Construcción y validación de los dos paquetes aislados |
| `scripts/create_pairing_record.py` | Método manual antiguo deshabilitado para evitar PIN sin protección |
| `scripts/refresh_event.py`, `events/` | Plantillas de pruebas; `admin-generate-pin.json` es exclusivo del administrador |
| `tests/` | Pruebas con mocks/dobles atómicos, concurrencia y aislamiento |
| `iam/` | Políticas de ejemplo para revisión y aplicación manual |
| `requirements.txt`, `requirements-admin.txt` | Dependencias fijadas con hashes SHA-256 |

## Nuevo flujo

1. Un administrador verifica por un canal confiable que el usuario Alexa está autorizado para el Thing.
2. Invoca manualmente `SmartParkPairingAdmin` con `allowedUserId` y `thingName`.
3. La Lambda valida formatos y llama una vez a `DescribeThing`. Genera `str(1000 + secrets.randbelow(9000))` y una generación UUID.
4. Una transacción de dos Put registra el hash `PAIR#…` y una ventana `PAIRUSER#<sha256(userId)>` en la **misma tabla existente**. No se almacena el PIN original.
5. Devuelve al operador `codigo`, `thingName` y `expiresInSeconds: 300`. No registra el resultado en logs. El operador copia el PIN en el simulador de Alexa.
6. Alexa recibe el slot `codigo`; valida su formato antes de consultar AWS y comprueba la vinculación actual.
7. `authorize_code()` decrementa atómicamente un intento en la ventana del usuario **antes de comparar el hash**. Si no hay ventana activa, expiró o no quedan intentos, rechaza. Un PIN incorrecto consume un intento y no consulta la fila PAIR de otro usuario.
8. Si coincide, lee la autorización por GetItem y valida destinatario, Thing, generación y caducidad. El handler también conserva DescribeThing.
9. `save_binding()` usa una sola transacción de tres acciones: elimina PAIR, guarda/reemplaza la vinculación con condición de revisión y marca la ventana `consumed` con cero intentos. Todo ocurre o nada ocurre. La reserva del intento anterior no se devuelve si falla la transacción.

Si se intenta cambiar al mismo Thing, también se consume el PIN; se evita dejar una autorización reutilizable. Las vinculaciones definitivas antiguas siguen siendo válidas. **Los códigos manuales antiguos sin ventana y los de doce dígitos dejan de autorizar nuevas vinculaciones.** No es necesario borrar vinculaciones existentes ni modificar sus Things.

## Protección del PIN corto

Hay solamente 9000 valores. SHA-256 no agrega entropía: quien pueda leer los hashes puede probar todo el espacio offline. La protección real es la combinación de **destinatario obligatorio, 300 segundos, tres intentos persistentes y autorización administrativa separada**.

- El contador reside en DynamoDB; no se repone al reiniciar Lambda ni al cambiar de contenedor.
- `UpdateItem` condicional serializa las reservas: treinta solicitudes simultáneas solo pueden obtener tres intentos. El tercero puede ser correcto.
- Cada candidato válido consume presupuesto, incluso el correcto o una llamada que después sufra un timeout. Los formatos imposibles se rechazan sin operaciones de datos y no permiten probar un PIN válido.
- No se puede generar otra ventana para el mismo usuario antes del vencimiento original, incluso si se consumió el código, se agotaron intentos o se desvinculó el parqueo. La generación administrativa no permite parámetros para aumentar TTL, intentos o forzar reinicio.
- Una autorización ya reservada tiene generación: no puede consumir una ventana nueva tras caducar la anterior.
- Un PIN activo global no se sobrescribe para otro usuario. Solo en colisión de PIN se prueban hasta tres candidatos, sin repetir DescribeThing. Si existe ventana del usuario, se detiene; errores de red no se reintentan.
- Los PIN caducados pueden reutilizarse en una generación nueva autorizada; el UUID impide que una autorización antigua se confunda con ella. Esto no permite reutilizar un registro consumido.
- No hay ruta de generación o reinicio desde los intents públicos. No se devuelven PIN en respuestas de Alexa.

Con una ventana autorizada y tres intentos, la probabilidad máxima de acertar por adivinación uniforme es aproximadamente **3/9000 = 0,033 % por ventana**. Esto es una reducción verificable de intentos para una demostración supervisada, **no autenticación fuerte para una barrera de producción**. Quien comparta la misma cuenta Alexa comparte `userId`; no se identifica la persona por voz. Un atacante puede gastar los tres intentos y causar denegación de vinculación, y las invocaciones rechazadas aún consumen AWS. Para producción, usar autorización de cuenta/posesión más fuerte; para una demo de mayor riesgo, hacer que el administrador registre directamente una asociación ya verificada en vez de aceptar un PIN público corto. El backend actual mantiene este flujo con intentos limitados para la práctica.

## Registros de DynamoDB

Los siguientes son esquemas documentales legibles, no códigos ni usuarios reales. Las llamadas boto3 usan AttributeValue.

```json
{
  "userId": "PAIR#<sha256-del-pin>",
  "recordType": "pairing",
  "thingName": "smartpark-grupo9-01",
  "allowedUserId": "amzn1.ask.account.USUARIO_AUTORIZADO",
  "expiresAt": 1794056700,
  "generation": "uuid-de-la-ventana"
}
```

```json
{
  "userId": "PAIRUSER#<sha256-del-userId>",
  "recordType": "pairing_window",
  "thingName": "smartpark-grupo9-01",
  "pairKey": "PAIR#<sha256-del-pin>",
  "generation": "uuid-de-la-ventana",
  "expiresAt": 1794056700,
  "remainingAttempts": 3,
  "status": "active"
}
```

La vinculación definitiva conserva `userId` Alexa, `thingName`, `fechaVinculacion`, `recordType: binding` y `revision`. No se crean tablas, índices ni procesos periódicos. La ventana permanece hasta su vencimiento incluso tras consumo, para no reponer intentos anticipadamente. No habilitar TTL sobre `expiresAt` sin revisar esta política; no es necesario para hacerla cumplir. Los registros expirados son inertes y pueden limpiarse administrativamente por clave, sin Scan en los handlers. El espacio de claves PAIR está acotado a 9000 posibles hashes y los expirados se reemplazan condicionalmente; hay una ventana por usuario participante.

## Preparación y construcción local

```sh
cd lambda
python3.13 -m venv .venv   # solo si no existe
sh scripts/build.sh
# Con wheels ya descargados:
BUILD_OFFLINE=1 sh scripts/build.sh
# Solo actualizar el ZIP de Alexa, conservando el administrativo:
BUILD_OFFLINE=1 sh scripts/build.sh alexa
```

Se reutiliza `.venv` Python 3.13; si el intérprete no está en PATH, usar `PYTHON313=/ruta/a/python3.13`. El script también detecta una instalación local de `uv`, sin descargar intérpretes. Descarga wheels universales con versiones/hashes fijados, instala dependencias en `.venv` y ejecuta `pip check`.

**Antes de empaquetar**, valida sintaxis y ejecuta todas las pruebas con sockets bloqueados. Después crea staging limpio por función, instala producción, copia solo su lista de código y valida el ZIP extraído con las pruebas correspondientes. Los dos handlers quedan en la raíz de sus respectivos paquetes.

| ZIP en `dist/` | Handler | Código administrativo incluido |
|---|---|---|
| `SmartParkAlexaBackend.zip` | `lambda_function.lambda_handler` | Ninguno: no contiene `admin_lambda_function.py` ni `administration/` |
| `SmartParkPairingAdmin.zip` | `admin_lambda_function.lambda_handler` | Solo administración y validación/política compartida; sin ASK ni handlers Alexa |

Se empaqueta boto3 completo y sus dependencias compatibles, evitando mezclar versiones con las del runtime. Alexa mantiene ASK Core 1.19.0, ASK Model 1.82.0, ASK Runtime 1.19.0 y boto3/botocore 1.43.126. El ZIP administrativo usa únicamente boto3/botocore, jmespath, python-dateutil, s3transfer, six y urllib3, con los mismos pins/hashes.

Solo se admiten wheels Python universales, sin `.so`, `.pyd` ni binarios macOS. Son portables a Linux x86_64 con Python 3.13. Una futura dependencia nativa deberá construirse para Lambda Linux x86_64; el empaquetado actual la rechaza. Ver [paquetes Python de Lambda](https://docs.aws.amazon.com/lambda/latest/dg/python-package.html).

El verificador inspecciona integridad, raíz, sintaxis, límites de carga directa, aislamiento, ausencia de `.venv`, cachés, tests, scripts, datos privados y claves. Los únicos PEM admitidos son los bundles públicos CA de botocore/certifi para HTTPS; no hay certificados del ESP32 ni secretos. El SDK ASK mantiene advertencias conocidas `SyntaxWarning` por escapes en fuentes de terceros bajo Python 3.13; no son errores y se conservan visibles.

Los informes `dist/build-report.json` y `dist/admin-build-report.json` registran tamaños exactos, SHA-256, pruebas y dependencias. Si una construcción falla, comprobar su exit code: puede permanecer el ZIP de una construcción anterior. ZIP y staging están ignorados por Git.

Pruebas sin empaquetar:

```sh
cd lambda
.venv/bin/python -B -m unittest discover -s tests -v
```

## Configuración manual en AWS — no ejecutada

### Lambda de Alexa existente

Subir `SmartParkAlexaBackend.zip` a **SmartParkAlexaBackend**, runtime Python 3.13, x86_64, 128 MB y timeout 10 s. Handler `lambda_function.lambda_handler`.

| Variable | Valor |
|---|---|
| `TABLE_NAME` | `SmartParkBindings` |
| `ALEXA_SKILL_ID` | Skill ID real `amzn1.ask.skill.…` |
| `IOT_DATA_ENDPOINT` | Recomendado: hostname ATS de datos, sin protocolo/rutas; evita DescribeEndpoint |
| `MAX_REPORTED_AGE_SECONDS` | Opcional, 180 por defecto |
| `AWS_REGION` | La proporciona Lambda; fallback local `us-east-1`, no sobrescribir variable reservada |

Conservar el trigger Alexa restringido al mismo Skill ID. No dar a esta Lambda permiso para invocar la administrativa. El JSON `admin: true` o un intent inventado no activa generación: no existe esa ruta ni está su código en el ZIP.

### Nueva Lambda administrativa a crear manualmente

Crear **SmartParkPairingAdmin**, runtime Python 3.13, arquitectura x86_64, 128 MB y timeout 10 s, con **rol de ejecución independiente**. Subir `SmartParkPairingAdmin.zip`. Handler: **`admin_lambda_function.lambda_handler`**.

Solo requiere `TABLE_NAME=SmartParkBindings`; `AWS_REGION` la proporciona Lambda. No necesita Skill ID, endpoint IoT Data ni credenciales estáticas. TTL e intentos son constantes internas, no variables ampliables desde eventos públicos.

**No configurar Function URL, API Gateway, trigger Alexa, triggers periódicos ni permisos para `alexa-appkit.amazon.com`.** La invocación manual debe estar limitada a un usuario/rol IAM administrativo confiable. No basta con comprobar un campo JSON: la frontera es otra función, otro rol y la política IAM que autoriza invocarla. Quien ya tenga permisos amplios `lambda:InvokeFunction` en la cuenta también debe ser considerado administrador; revisar esas políticas. No habilitar logging de payloads/retornos, tracing de datos sensibles ni copiar el PIN en descripciones de eventos guardados.

### Permisos IAM mínimos preparados

Reemplazar `REEMPLAZAR_ACCOUNT_ID` y los Things autorizados en los ejemplos de `iam/`. Son políticas para revisión; **no fueron aplicadas ni validadas contra IAM real**.

- `admin-execution-policy.example.json`: `iot:DescribeThing` solo sobre Things gestionados y `dynamodb:PutItem` solo sobre `SmartParkBindings`, con `LeadingKeys` `PAIR#*` y `PAIRUSER#*`. La transacción de generación contiene dos Put, no requiere Scan, GetItem, UpdateItem ni operaciones Shadow.
- `admin-invoke-policy.example.json`: `lambda:InvokeFunction` únicamente sobre `SmartParkPairingAdmin`, para el operador confiable. No asociarla al rol de Alexa ni al usuario final.
- `execution-role-trust.example.json`: confianza de los roles de ejecución en `lambda.amazonaws.com`, no en usuarios ni en Alexa. Es distinta del permiso del operador para invocar.
- `alexa-execution-policy.example.json`: GetItem en vinculaciones/PAIR, PutItem solo vinculaciones, DeleteItem en vinculaciones/PAIR, **UpdateItem solo en ventanas PAIRUSER**, y permisos IoT necesarios. Sin Put de códigos/ventanas ni invocación de otras Lambdas. Retirar `iot:DescribeEndpoint` si se configura el endpoint y se elimina el descubrimiento de la aplicación, o conservarlo con el diseño actual.

Los permisos de transacciones DynamoDB corresponden a las acciones subyacentes PutItem/DeleteItem/UpdateItem; no añadir una acción IAM ficticia `dynamodb:TransactWriteItems`. Referencia: [IAM con transacciones](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis-iam.html). Conservar además permisos básicos para logs, restringidos al log group de cada función si se administran manualmente.

El rol Alexa actual tenía FullAccess. **Añadir una política reducida no cancela FullAccess**: para aplicar realmente esta separación de privilegios, reemplazar las políticas amplias tras revisar y probar manualmente los permisos. El administrador también debe verificar por un canal confiable que `allowedUserId` esté autorizado para `thingName`; DescribeThing por sí solo no demuestra propiedad física.

## Generar un PIN desde AWS

En Test de **SmartParkPairingAdmin**, ejecutar una sola vez este evento con valores reales:

```json
{
  "allowedUserId": "amzn1.ask.account.USUARIO_AUTORIZADO",
  "thingName": "smartpark-grupo9-01"
}
```

Obtener `allowedUserId` del JSON Input de una petición real del usuario en el simulador Alexa, sin añadirlo a logs ni al repositorio. El nombre del Thing es solo un ejemplo y no está fijado en la lógica.

La respuesta administrativa exitosa tiene esta forma (PIN ilustrativo):

```json
{
  "codigo": "5831",
  "thingName": "smartpark-grupo9-01",
  "expiresInSeconds": 300
}
```

Copiarlo inmediatamente al simulador. Si hay un `error`, no hay un PIN nuevo confirmado para usar. Una respuesta perdida o un timeout puede ocurrir después de guardar la ventana: no reintentar automáticamente ni forzar su borrado; esperar hasta cinco minutos desde la generación antes de emitir otro PIN. El original no se puede recuperar desde el hash. La función solo reintenta colisiones de candidato, hasta tres veces, cuando AWS identifica esa condición; ante cancelación no identificable falla de forma conservadora.

## Configurar Alexa y probar

Mantener todos los nombres de intents. En `VincularParqueoIntent` y `CambiarVinculacionIntent`, configurar **slot `codigo` como `AMAZON.FOUR_DIGIT_NUMBER`**, construir el modelo y probar el locale español. Revisar que el JSON Input contenga una cadena de cuatro dígitos: el backend valida la cadena entregada por el SDK y no interpreta frases de números arbitrarias.

La [referencia oficial de slots Alexa](https://developer.amazon.com/en-US/docs/alexa/custom-skills/slot-type-reference.html) describe este tipo. La disponibilidad y el reconocimiento deben comprobarse en el locale utilizado.

| Intent | Frase de ejemplo |
|---|---|
| `VincularParqueoIntent` | vincula mi parqueo con el código {codigo} |
| `CambiarVinculacionIntent` | cambia mi vinculación con el código {codigo} |
| `DesvincularParqueoIntent` | desvincula mi parqueo |
| `AbrirBarreraIntent` / `CerrarBarreraIntent` | abrir; abre la barrera / cerrar; cierra la barrera |
| `ConsultarDistanciaIntent` | consultar distancia; a qué distancia está el vehículo |
| `ConsultarVehiculoIntent` | consultar vehículo; hay un vehículo esperando |
| `EstadoBarreraIntent` | consultar estado; consulta el estado de la barrera |
| `AMAZON.HelpIntent`, `CancelIntent`, `StopIntent`, `FallbackIntent` | ayuda, cancela, salir y solicitudes no reconocidas |

1. Subir/configurar ambos paquetes manualmente y comprobar IAM/trigger antes de probar.
2. Generar el PIN en la Lambda administrativa para el usuario real.
3. En Alexa: “abre parqueo inteligente”, después “vincula mi parqueo con el código …”. Todos los mensajes ahora indican **cuatro dígitos**. No pronunciar el PIN de un usuario distinto.
4. Verificar la confirmación de vinculación. Probar una consulta y una sola apertura/cierre; las respuestas conservan la distinción entre solicitud y reporte físico estimado.
5. Para cambiar: generar otro PIN cuando termine la ventana anterior y decir “cambia mi vinculación con el código …”. Desvincular no borra ni reabre la ventana de intentos.
6. Para comprobar consumo, hacer lecturas puntuales por clave en DynamoDB: la fila `PAIR#<hash>` ya no existe, la vinculación `userId` tiene el Thing y la ventana `PAIRUSER#<hash-user>` tiene `status=consumed`, `remainingAttempts=0`. No usar Scan ni bucles de consulta. Conocer hashes/IDs también es información administrativa: no publicarlos.
7. Para derivar las claves localmente, desde `lambda/` usar Python y entrada privada `getpass`, sin poner PIN/userId en argumentos de shell:

   ```sh
   .venv/bin/python -B - <<'PY'
   from getpass import getpass
   from services.validation import pairing_key
   from services.pairing_policy import pairing_window_key
   print(pairing_key(getpass('PIN consumido: ')))
   print(pairing_window_key(getpass('userId Alexa: ')))
   PY
   ```

Los JSON `events/link.json` y `change-binding.json` contienen un PIN **ficticio no registrado**; reemplazarlo. Actualizar IDs en session/context y timestamp con `scripts/refresh_event.py` antes de pruebas Lambda; se conserva la validación de peticiones de hasta 150 s. `events/admin-generate-pin.json` no es un evento Alexa y solo se debe ejecutar en la función administrativa.

## Conversación continua dentro de SmartPark

Después de respuestas correctas de abrir, cerrar, consultar estado, distancia o presencia, el backend emite `shouldEndSession: false` y un `reprompt` mediante ASK SDK. `say()` mantiene el cierre por defecto: solo los handlers de éxito seleccionados piden continuar. Tras una orden física, se conserva “Solicité …” y el reprompt propone consultar estado/distancia o salir, sin afirmar que el servo ya terminó ni invitar a repetir la orden.

Ejemplo con un usuario ya vinculado, respondiendo mientras Alexa está escuchando:

```text
Usuario: Alexa, abre parqueo inteligente.
Alexa: Bienvenido a parqueo inteligente. Puedes decir abrir, consultar estado, cerrar o salir.
Usuario: abrir.
Alexa: Solicité abrir la barrera. Puedes consultar su estado para conocer el último reporte del dispositivo.
Usuario: consultar estado.
Alexa: Según el último estado reportado, la barrera está abierta.
Usuario: cerrar.
Alexa: Solicité cerrar la barrera. Puedes consultar su estado para conocer el último reporte del dispositivo.
Usuario: salir.
Alexa: Hasta luego.
```

El estado del ejemplo depende del reporte real: una consulta inmediata puede devolver todavía el estado anterior o señalar datos antiguos. Cada orden se responde y se espera el siguiente turno del usuario; no se emiten consultas adicionales para completar el movimiento.

**Agregar las frases cortas en Alexa Developer Console** a los intents correspondientes de la tabla anterior y construir el modelo del locale que uses. Conservar las frases largas existentes. Comprobar en JSON Input que “abrir”, “cerrar”, “consultar estado”, “consultar distancia” y “consultar vehículo” llegan a sus intents actuales; comprobar que “salir” llega a `AMAZON.StopIntent` y “cancelar” a `AMAZON.CancelIntent`. El backend no hace reconocimiento de texto libre: las pruebas de eventos verifican dispatch y respuestas, no el reconocimiento de voz del modelo Alexa.

Help y Fallback ofrecen esos comandos y una salida clara. Stop/Cancel cierran con `shouldEndSession: true`, sin reprompt. `SessionEndedRequest` recibe respuesta vacía, sin voz ni reprompt, y nunca reabre una sesión terminada. Los errores mantienen cierre por defecto, especialmente timeouts tras una acción que pudo haber sido aceptada. Tras un fallo, volver a abrir la skill y consultar el estado antes de repetir una orden física.

La conversación **no es indefinida**. `shouldEndSession: false` permite a Alexa escuchar unos segundos y, si corresponde, pronunciar el reprompt y volver a escuchar brevemente. El silencio, la salida del usuario, errores o las reglas de sesión de Alexa pueden terminarla. Una vez cerrada, volver a decir “Alexa, abre parqueo inteligente”. Ver [gestión oficial de sesiones Alexa](https://developer.amazon.com/en-US/docs/alexa/custom-skills/manage-skill-session-and-session-attributes.html). No se modifica la duración oficial ni se mantiene Lambda ejecutándose entre turnos.

Los ejemplos `events/open.json`, `close.json`, `barrier-status.json`, `distance.json`, `vehicle.json`, `help.json`, `stop.json`, `cancel.json` y `fallback.json` ahora usan `session.new: false` para ilustrar turnos dentro de la sesión. `events/session-ended.json` ilustra el cierre notificado por Alexa. Son eventos individuales para Test de Lambda; actualizar timestamp e IDs con el helper existente. Una secuencia de JSON manual no mantiene por sí sola una sesión de voz en el dispositivo: esa comprobación se hace en el simulador/Echo tras configurar las frases.

No se cambió la lógica PIN, DynamoDB, la función administrativa, el firmware ni el acceso al Shadow. Mantener la sesión abierta no genera polling, heartbeat ni llamadas AWS en espera; cada petición recibida conserva sus operaciones de datos originales. Más órdenes voluntarias del usuario implican más invocaciones normales.

## Consumo y comportamiento conservado

No se agregaron polling, programación, colas, bases de datos ni servicios intermedios. Generación normal: **1 DescribeThing y 1 transacción de dos escrituras**. Cada guess con formato válido y usuario con flujo de vinculación apropiado hace 1 UpdateItem condicional; si falla el hash se detiene. La vinculación correcta completa: GetItem de vinculación, UpdateItem de intento, GetItem de PAIR, DescribeThing y transacción de tres acciones. La escritura adicional de ventana es el costo deliberado de limitar un PIN corto con concurrencia.

Abrir/cerrar, consultas, desvinculación, ayuda y salida conservan sus llamadas y semántica. Las consultas siguen leyendo exclusivamente reported con frescura de metadata por campo. Las órdenes escriben solo desired.barrera; no hay GET previo ni espera activa de confirmación. No se cachean vinculaciones entre usuarios; sí se reutilizan clientes. SDK con un intento por llamada, conexión de 0,5 s y lectura de 1 s por llamada; no hay reintentos ilimitados.

Logs propios: solo tipo de errores de servicio/inesperados, nunca PIN, hashes, eventos, userId completo, Thing ni tokens. No se imprime el resultado administrativo. Las consolas de Test y la respuesta de Invoke son canales privados del operador: contienen el PIN por diseño y deben protegerse. Revisar cualquier configuración externa que capture payloads. Los registros estándar de Lambda y las operaciones rechazadas también pueden tener costo.

Revisar Billing, elegibilidad/créditos, duración/memoria de ambas Lambdas, CloudWatch Logs, almacenamiento y escrituras transaccionales DynamoDB y operaciones IoT. El presupuesto del firmware **no limita el backend**. No se garantiza costo cero. La Lambda administrativa nueva tiene consumo solo al ejecutarse, pero crearla y usarla requiere configuración y supervisión de la cuenta; no se creó automáticamente.

## Alcance de las pruebas

Se prueban generación segura y rango, normalización/formato, PIN incorrecto/expirado/usado, usuario no autorizado, Thing inexistente, vincular/cambiar/desvincular, revisión concurrente, tres intentos persistentes incluso con hilos, último intento correcto, consumo único, una sola ventana concurrente, bloqueo de regeneración, colisiones limitadas, errores de servicios, aislamiento de entradas/ZIP y logs sanitizados. Se conservan las pruebas de sensores, Shadow y respuestas del SDK.

Son **pruebas con dobles**, no pruebas AWS reales. Los ZIP se importan y prueban offline bajo Python 3.13, con dependencias universales; no se ejecutó el runtime Linux de Lambda ni se validaron IAM, reconocimiento del slot, apertura física o Billing en la cuenta. No se desplegaron funciones, crearon recursos ni realizaron commits/pushes.

## Resultado anterior: PIN de cuatro dígitos

- Python 3.13.16; sintaxis, `pip check` e integridad: PASS.
- **83 pruebas locales** previas al empaquetado: OK (dobles/mocks; sockets bloqueados).
- ZIP Alexa extraído, sin acceso a dependencias de `.venv`: **66 pruebas, OK**. Handler raíz importable.
- ZIP administrativo extraído, sin dependencias ASK ni acceso a `.venv`: **15 pruebas, OK**. Handler raíz importable.
- Dos pruebas adicionales de integración/aislamiento se ejecutan antes de construir los ZIP; los códigos administrativos no están en el paquete Alexa.
- `SmartParkAlexaBackend.zip`: **18.359.880 bytes** comprimidos; 27.374.077 bytes descomprimidos. SHA-256 `66b2ffff2fc4289772406422a987ffbc1a030a37349e28f8f223e421b661d3df`.
- `SmartParkPairingAdmin.zip`: **16.869.763 bytes** comprimidos; 23.118.436 bytes descomprimidos. SHA-256 `87d4ce398ee40b6412a51c06b1f10b80f6f96413f379b450eeb0f17fc2200155`.
- Ambos por debajo de los límites verificados de carga directa (50 MiB comprimidos, 250 MiB descomprimidos), sin carpeta contenedora ni secretos del proyecto. Los bundles CA públicos de dependencias son la excepción HTTPS documentada.
- Los archivos fuente de ambos paquetes fueron cotejados contra el código final; la verificación no representa una ejecución real en AWS/Linux ni una evaluación real de políticas IAM.

## Resultado actual: conversación continua

- **91 pruebas locales, OK**, ejecutadas con mocks/dobles y sockets bloqueados antes de empaquetar.
- **74 pruebas sobre el ZIP Alexa extraído, OK**, sin usar dependencias de `.venv`; handler raíz `lambda_function.lambda_handler` importable.
- Nueva cobertura: cinco intents con `shouldEndSession=false` y reprompt, varios turnos en una sesión, Stop/Cancel, SessionEndedRequest, Help/Fallback, errores/timeout y conteos de llamadas AWS sin incrementos.
- `dist/SmartParkAlexaBackend.zip`: **18.360.025 bytes** comprimidos; 27.374.557 bytes descomprimidos. SHA-256 `223bfd422e9aa45389629b5ab5931d7ee2d92b5d1748b9e7cbbf8d72daa5faf2`.
- Validaciones de sintaxis, integridad, estructura y código final: PASS. El paquete administrativo y la lógica PIN/servicios se cotejaron por hash y permanecen intactos.
- Pendiente: cargar manualmente el ZIP Alexa, agregar/construir frases cortas en Developer Console y comprobar voz, tiempos de escucha y sesión real en simulador/Echo. No se probó AWS real ni se desplegó nada.

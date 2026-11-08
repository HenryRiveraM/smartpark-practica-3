# Pruebas funcionales PF-03, PF-04, PF-05 y PF-06

## 1. Descripción

Estas pruebas funcionales tienen como objetivo verificar la integración del sistema de parqueo inteligente con AWS IoT Device Shadow y Alexa. Se busca comprobar la actualización de los estados del dispositivo, el control de la barrera mediante comandos de voz y la consulta de información del sistema a través de Alexa.

## 2. Objetivos

- **PF-03:** Verificar que AWS IoT Device Shadow actualice correctamente la información de distancia y detección de vehículos.
- **PF-04:** Comprobar que Alexa permita abrir la barrera mediante un comando de voz.
- **PF-05:** Comprobar que Alexa permita cerrar la barrera mediante un comando de voz.
- **PF-06:** Verificar que Alexa pueda proporcionar información sobre la distancia, la detección de vehículos y el estado general del sistema.

## 3. Procedimiento

### PF-03 — Actualización de AWS IoT Device Shadow

**Requerimientos relacionados:** RF2, RF4.

1. Encender el ESP32 y verificar que se encuentre conectado a Internet.
2. Ingresar a AWS IoT Core.
3. Acceder al Device Shadow correspondiente al dispositivo.
4. Observar los valores registrados en la sección `reported`.
5. Acercar un objeto al sensor ultrasónico.
6. Verificar que se actualicen los valores de `distancia_cm` y `vehiculo_detectado`.
7. Alejar el objeto y comprobar nuevamente la actualización de los valores reportados.

**Resultado esperado:**

El Device Shadow debe reflejar los cambios detectados por el sensor ultrasónico, actualizando los atributos `distancia_cm` y `vehiculo_detectado` dentro de `reported`.

### PF-04 — Apertura de barrera mediante Alexa

**Requerimientos relacionados:** RF3, RF5.

1. Verificar que el ESP32 y el servomotor se encuentren conectados y funcionando.
2. Activar la skill de Alexa correspondiente al sistema de parqueo inteligente.
3. Pronunciar el comando: «Alexa, abre parqueo inteligente».
4. Una vez iniciada la skill, decir: «abrir».
5. Observar el movimiento del servomotor.
6. Verificar el estado de la barrera en AWS IoT Device Shadow.

**Resultado esperado:**

El servomotor debe girar hasta los 90° y el atributo `reported.barrera` debe actualizarse al estado `abierta`.

### PF-05 — Cierre de barrera mediante Alexa

**Requerimientos relacionados:** RF3, RF5.

1. Mantener activa la skill de Alexa del sistema de parqueo inteligente.
2. Pronunciar el comando: «cerrar la barrera».
3. Observar el movimiento del servomotor.
4. Verificar que la barrera regrese a su posición inicial.
5. Comprobar el estado reportado en AWS IoT Device Shadow.

**Resultado esperado:**

El servomotor debe girar hasta los 0° y el atributo `reported.barrera` debe actualizarse al estado `cerrada`.

### PF-06 — Consulta de información mediante Alexa

**Requerimientos relacionados:** RF4, RF6.

1. Activar la skill de Alexa del sistema de parqueo inteligente.
2. Pronunciar el comando: «consultar distancia».
3. Verificar que Alexa responda con la distancia registrada por el sensor ultrasónico.
4. Pronunciar el comando: «consultar vehículo».
5. Verificar que Alexa informe si existe un vehículo detectado.
6. Pronunciar el comando: «consultar estado».
7. Comprobar que Alexa proporcione el estado actual del sistema.

**Resultado esperado:**

Alexa debe responder en español utilizando los valores reportados por el dispositivo, proporcionando información sobre la distancia, la detección de vehículos y el estado general del sistema.

## 4. Resultados y evidencias

Se cuenta con los siguientes archivos de evidencia:

| Archivo | Descripción |
|---|---|
| `pf03.mp4` | Video de la prueba de actualización de AWS IoT Device Shadow. |
| `pf04-05-062.mp4` | Video relacionado con las pruebas de apertura y cierre mediante Alexa. |
| `pf04-05-063.mp4` | Video complementario de las pruebas de apertura y cierre. |
| `PF04 - pf05.xlsx` | Registro de los comandos de voz y los estados esperados para tres repeticiones. |

### Registro de pruebas PF-04 y PF-05

En el archivo Excel se registran tres repeticiones de los siguientes comandos:

| Comando de voz | Estado esperado |
|---|---|
| Alexa, abre parqueo inteligente | Abierta |
| Cerrar la barrera | Cerrada |

### Observaciones

- PF-03 cuenta con un video de evidencia de la observación del Device Shadow.
- PF-04 y PF-05 cuentan con videos y un registro de los comandos y estados esperados.
- PF-06 no cuenta con un registro independiente de las respuestas obtenidas para los tres comandos de consulta.

## 5. Resultado de las pruebas

Las cuatro pruebas están orientadas a verificar la comunicación entre el ESP32, AWS IoT Core y Alexa.

Los archivos proporcionados documentan parte de la ejecución y los resultados esperados. Sin embargo, para declarar las pruebas como aprobadas es necesario confirmar que cada comportamiento esperado se haya producido correctamente:

- **PF-03:** Confirmar la actualización de `distancia_cm` y `vehiculo_detectado` en `reported`.
- **PF-04:** Confirmar el movimiento del servomotor a 90° y el estado `abierta`.
- **PF-05:** Confirmar el movimiento del servomotor a 0° y el estado `cerrada`.
- **PF-06:** Confirmar que Alexa responda correctamente a las tres consultas en español.

Por tanto, las pruebas quedan pendientes de validación final hasta completar la comprobación de sus resultados esperados.
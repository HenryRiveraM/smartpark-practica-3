# SmartPark — fase 1

Firmware Arduino/C++ para ESP32 DOIT DEVKIT V1, HC-SR04 y SG90. El sensor informa presencia; **solo los comandos Serial abren o cierran la barrera**. Al arrancar se ordena cerrar. No hay conexión Wi-Fi ni servicios cloud.

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

## Estructura y configuración

- `include/config.h`: pines, tiempos, umbrales, rango útil de 2–400 cm, PWM, ángulos y calibración. Ajustar `monitor_speed` en `platformio.ini` si cambia `SERIAL_BAUD`.
- `UltrasonicSensor`: inicialización, pulso, medida y presencia, sin referencia al servo. Cada resultado contiene validez y tiempo; la distancia solo es utilizable si el estado es `Valid`.
- `BarrierServo`: interfaz `open()`, `close()`, `commandedState()`, `moving()` y `positionEstimated()`. `begin()` devuelve si se pudo asignar PWM, no si hay un servo conectado. Las órdenes repetidas no reenvían PWM ni reinician el temporizador. Una orden contraria durante un movimiento inicia una nueva estimación.
- `SerialCommands`: parser con buffer fijo, sin asignación dinámica. `main.cpp` coordina tareas y presentación.
- `include/config.h` usa macros `#define` e incluye Wi-Fi, endpoint, nombre del Thing, topicos y tiempos de reconexion como configuracion futura; no activa conectividad. `THING_NAME` debe coincidir con el dispositivo registrado en AWS. Contiene datos locales de Wi-Fi: reemplazarlos por valores de ejemplo antes de publicar el archivo.
- `include/secrets.h`: bloques PEM `AWS_ROOT_CA`, `AWS_DEVICE_CERT` y `AWS_PRIVATE_KEY` con `PROGMEM`, ignorado por Git y sin uso en esta fase. Los bloques vacios no son credenciales validas. En una copia nueva crear con `cp include/secrets.example.h include/secrets.h`. No compartir certificados privados ni claves.

Dependencias fijadas: plataforma `espressif32@7.1.0` (Arduino ESP32 2.0.17) y [ESP32Servo 1.1.2](https://github.com/madhephaestus/ESP32Servo/tree/1.1.2), obtenida directamente de la etiqueta Git de GitHub porque el registro de PlatformIO no resuelve esa versión. Requiere Git instalado y acceso a GitHub. Compatible con esta generación de Arduino. PWM a 50 Hz con pulsos de 1000–2000 µs como punto de partida conservador; el ángulo real depende del servo y del montaje. No actualizar a otra versión mayor de la biblioteca sin verificar compatibilidad con el core Arduino.

## Compilar, cargar y monitorizar

Instalar PlatformIO Core o la extensión PlatformIO de VS Code. Desde la raíz:

```sh
pio run
pio device list
pio run -t upload --upload-port /dev/cu.usbserial-TU_PUERTO
pio device monitor --port /dev/cu.usbserial-TU_PUERTO --baud 115200
```

Sustituir el puerto por el mostrado por `pio device list` (en Windows, por ejemplo `COM3`). Cerrar otros monitores antes de cargar. Si la placa no entra al bootloader, mantener BOOT durante el inicio de conexión de la carga y soltar al comenzar la escritura. También están disponibles las acciones Build, Upload y Monitor de PlatformIO. En este equipo el ejecutable existe en `~/.platformio/penv/bin/pio`, aunque no está en PATH.

## Comandos Serial

Enviar cada comando terminado en LF, CR o CRLF; se aceptan minúsculas y espacios exteriores.

| Comando | Resultado |
|---|---|
| `OPEN` | Orden de apertura |
| `CLOSE` | Orden de cierre |
| `STATUS` | Última medida, edad, presencia, orden y movimiento estimado |
| `DISTANCE` | Última medida y presencia; no fuerza una lectura |
| `HELP` | Ayuda |

Líneas desconocidas, con controles inválidos o de más de 31 caracteres se descartan. Una línea parcial espera su terminador sin bloquear otras tareas. Se procesan hasta 64 bytes por vuelta. No inundar el puerto: el buffer UART es finito.

## Medición y estados

La lectura ocurre cada 500 ms mediante diferencias sin signo de `millis()`, tolerando su desbordamiento. `pulseIn()` bloquea como máximo el timeout configurado (30 ms nominales), más pulso TRIG de 12 µs y sobrecarga. Esto puede retrasar comandos durante la medición. La salida Serial también puede esperar espacio en su buffer; no es un sistema de tiempo real estricto.

Presencia: distancia ≤15 cm establece SI; distancia ≥18 cm establece NO. Entre ambos límites conserva el estado anterior. La primera lectura válida dentro de la banda, o una tras un fallo, establece NO hasta alcanzar ≤15 cm. Timeout o distancia fuera de rango producen DESCONOCIDO y nunca se imprimen como 0 cm ni activan una detección. La velocidad del sonido es una aproximación sin compensación térmica.

Al arrancar o recibir una orden distinta se envía el ángulo y comienza una ventana estimada de 700 ms. Transcurrida esta ventana solo se estima que hubo tiempo para el movimiento. No hay realimentación de posición, detección de servo desconectado o atascado ni garantía de movimiento físico. Se mantiene PWM para sostener la posición. La presencia nunca envía órdenes al servo.

## Pruebas sin hardware

Con compilador C++17 del equipo:

```sh
sh test/run_host_tests.sh
```

Compila los archivos reales del firmware contra dobles de Arduino/ESP32Servo en un directorio temporal. Comprueba inicialización y pulso del sensor, conversión, timeout, fuera de rango, detección, histéresis, fallo de asignación PWM, apertura/cierre, órdenes redundantes, duración estimada y desbordamiento temporal. También verifica parser (comandos, líneas parciales, CRLF, exceso de longitud y recuperación) y `setup()`/`loop()` con lecturas y comandos simultáneos, tráfico Serial acotado y ausencia de apertura por detección. Estos dobles verifican lógica, no comportamiento eléctrico ni temporización física. No requieren instalar las dependencias de PlatformIO.

## Pruebas de banco pendientes

No se ejecutaron pruebas físicas ni se cargó firmware a un dispositivo durante esta implementación.

1. Revisar alimentación, tierra y adaptación de ECHO antes de conectar el ESP32. Con servo sin varilla, reiniciar y observar orden CERRADA y transición de movimiento estimado en `STATUS`; comprobar físicamente el cierre.
2. Colocar superficies planas a 10, 20 y 100 cm; comparar medida con regla. A 10 cm debe indicar SI y a 20 cm NO, manteniendo siempre la barrera cerrada.
3. Pasar de 12 a 16 a 20 a 16 a 12 cm: esperar SI, SI, NO, NO, SI. Esperar al menos una lectura entre posiciones.
4. Sin blanco dentro del rango, o retirando ECHO con alimentación desconectada antes de modificar cables, comprobar timeout/presencia desconocida. Verificar que sigue aceptando `HELP` y órdenes.
5. Enviar `OPEN`, esperar y comprobar desplazamiento físico; repetir `OPEN` y verificar que no se reinicia la estimación. Enviar `CLOSE`. Revisar ángulos y pulsos sin forzar topes.
6. Probar `STATUS`, `DISTANCE`, `HELP`, minúsculas, CRLF, comandos inválidos, línea larga y comando parcial. Verificar recuperación con la siguiente línea válida.
7. Mientras llegan medidas cada 500 ms, alternar `OPEN`/`CLOSE` y comprobar continuidad, estabilidad de alimentación y respuesta (con posible espera de la lectura ultrasónica). Probar órdenes opuestas antes de 700 ms.

## Próxima fase

Agregar un servicio de conectividad que consulte la interfaz del sensor y ordene al servo. AWS IoT Core, MQTT, Device Shadow, Lambda, DynamoDB y Alexa quedan pendientes; esta fase solo reserva la configuracion y plantillas PEM; no incluye conexion de red, pantalla, LEDs, segundo sensor, conteo ni apertura automática.

## Verificación de esta implementación

`sh test/run_host_tests.sh`: PASS, compilado con advertencias tratadas como errores.

Se intentó `pio run`: el directorio global de PlatformIO no permite escritura desde esta sesión. Se repitió con `PLATFORMIO_CORE_DIR=/tmp/smartpark-pio-core`, reutilizando los paquetes instalados; intentó instalar la dependencia ESP32Servo y terminó con `HTTPClientError` antes de descargarla. Una comprobación independiente devolvió fallo de resolución DNS. Por ello **la compilación y enlace para ESP32 no están verificados**; no se obtuvo un binario validado ni se realizó carga. Repetir `pio run` en un entorno con acceso al registro de PlatformIO y permisos de escritura en su directorio de paquetes.

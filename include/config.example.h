#pragma once

#include <Arduino.h>

// ============================================================
// Configuracion del proyecto SmartPark.
// Modificar aqui los parametros antes de compilar.
// Certificados y clave privada: secrets.h (no subir a Git).
// Conectividad de fase 2. Wi-Fi y PEM se definen en secrets.h.
// ============================================================

// ---------- Red Wi-Fi ----------

// ---------- AWS IoT Core ----------
// Endpoint sin protocolo, rutas ni el sufijo de ejemplo.
#define AWS_IOT_ENDPOINT   "a1acybki981kqw-ats.iot.us-east-1.amazonaws.com"
#define MQTT_PORT          8883
#define THING_NAME         "smartpark-grupo9-01" // Debe coincidir con el Thing creado en AWS.
#define MQTT_BUFFER_SIZE   1024

// ---------- Topicos Device Shadow ----------
#define TOPIC_SHADOW_UPDATE "$aws/things/" THING_NAME "/shadow/update"
#define TOPIC_SHADOW_DELTA  "$aws/things/" THING_NAME "/shadow/update/delta"

#define TOPIC_SHADOW_GET \
    "$aws/things/" THING_NAME "/shadow/get"

#define TOPIC_SHADOW_GET_ACCEPTED \
    "$aws/things/" THING_NAME "/shadow/get/accepted"

#define TOPIC_SHADOW_GET_REJECTED \
    "$aws/things/" THING_NAME "/shadow/get/rejected"

#define TOPIC_SHADOW_UPDATE_ACCEPTED \
    "$aws/things/" THING_NAME "/shadow/update/accepted"

#define TOPIC_SHADOW_UPDATE_REJECTED \
    "$aws/things/" THING_NAME "/shadow/update/rejected"

// ---------- Sensor HC-SR04 ----------
#define TRIG_PIN                  32
#define ECHO_PIN                  35 // Adaptar ECHO de 5 V a 3,3 V.
#define SENSOR_INTERVAL_MS        500UL
#define ECHO_TIMEOUT_US           30000UL
#define TRIG_LOW_US               2UL
#define TRIG_HIGH_US              10UL
#define SOUND_CM_PER_US           0.0343f
#define MIN_DISTANCE_CM           2.0f
#define MAX_DISTANCE_CM           400.0f
#define VEHICLE_DETECTION_CM      15.0f
#define DETECTION_HYSTERESIS_CM    3.0f

// ---------- Barrera / servo SG90 ----------
#define SERVO_PIN                 25
#define BARRIER_CLOSED_ANGLE      0
#define BARRIER_OPEN_ANGLE        90
#define SERVO_FREQUENCY_HZ        50
// Rango verificado con el servo: 0 grados = 500 us, 90 grados = 1450 us.
#define SERVO_MIN_US              500
#define SERVO_MAX_US              2400
#define SERVO_TRAVEL_MS           700UL // Estimacion, sin confirmacion fisica.

// ---------- Tiempos de reconexion ----------
#define WIFI_RETRY_INTERVAL_MS    5000UL
#define MQTT_RETRY_INTERVAL_MS    5000UL

// ---------- Depuracion y comandos Serial ----------
#define SERIAL_BAUD               115200
#define COMMAND_CAPACITY          32
#define SERIAL_BYTES_PER_LOOP     64

// ---------- Validaciones de configuracion ----------
static_assert(BARRIER_CLOSED_ANGLE >= 0 && BARRIER_CLOSED_ANGLE <= 180, "Angulo cerrado invalido");
static_assert(BARRIER_OPEN_ANGLE >= 0 && BARRIER_OPEN_ANGLE <= 180, "Angulo abierto invalido");
static_assert(SERVO_MIN_US < SERVO_MAX_US, "Calibracion invalida");
static_assert(VEHICLE_DETECTION_CM >= MIN_DISTANCE_CM &&
              VEHICLE_DETECTION_CM + DETECTION_HYSTERESIS_CM <= MAX_DISTANCE_CM &&
              DETECTION_HYSTERESIS_CM >= 0, "Umbrales invalidos");

// Limites locales academicos: NO son cuotas gratuitas oficiales de AWS.
#define AWS_REPORT_INTERVAL_MS             30000UL
#define AWS_MIN_PUBLISH_INTERVAL_MS         10000UL
#define AWS_DISTANCE_CHANGE_THRESHOLD_CM   10.0f
#define AWS_MAX_SHADOW_UPDATES_PER_DAY      1000U
#define AWS_RESERVED_CONTROL_UPDATES       200U
#define AWS_PRESENCE_STABLE_SAMPLES         3U
#define AWS_DEMO_MAX_CONNECTED_MS          3600000UL // 0 desactiva el limite
#define AWS_RETRY_MAX_MS                   300000UL
#define AWS_MAX_CONNECTION_ATTEMPTS        10U
#define AWS_SHADOW_RESPONSE_TIMEOUT_MS     15000UL
#define AWS_MAX_REQUEST_ATTEMPTS           3U
#define AWS_STATUS_INTERVAL_MS             30000UL
#define AWS_NTP_TIMEOUT_MS                 30000UL
#define AWS_MIN_VALID_EPOCH                1767225600LL // 2026-01-01 UTC
static_assert(AWS_RESERVED_CONTROL_UPDATES < AWS_MAX_SHADOW_UPDATES_PER_DAY, "Reserva invalida");
static_assert(AWS_PRESENCE_STABLE_SAMPLES > 0, "Estabilidad invalida");
static_assert(AWS_RETRY_MAX_MS >= 1000 && AWS_RETRY_MAX_MS < 0x80000000UL, "Backoff invalido");
static_assert(AWS_MAX_CONNECTION_ATTEMPTS > 0 && AWS_MAX_REQUEST_ATTEMPTS > 0, "Reintentos invalidos");
static_assert(AWS_REPORT_INTERVAL_MS > 0 && AWS_MIN_PUBLISH_INTERVAL_MS > 0, "Intervalos invalidos");

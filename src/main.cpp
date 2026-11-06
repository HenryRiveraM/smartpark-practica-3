#include <Arduino.h>
#include "config.h"
#include "UltrasonicSensor.h"
#include "BarrierServo.h"
#include "SerialCommands.h"
namespace {
UltrasonicSensor sensor;
BarrierServo barrier;
SerialCommands commands;
uint32_t lastSampleMs = 0;
void printBarrier() {
    if (!barrier.initialized()) { Serial.println("Servo: fallo de asignacion PWM"); return; }
    Serial.print("Barrera ordenada: ");
    Serial.println(barrier.commandedState() == BarrierServo::State::Open ? "ABIERTA" : "CERRADA");
    Serial.println(barrier.moving() ? "Movimiento: en curso (estimado)" : "Posicion: estimada por tiempo, sin confirmacion fisica");
}
void printDistance() {
    const auto& reading = sensor.lastMeasurement();
    switch (reading.status) {
    case UltrasonicSensor::ReadingStatus::Valid:
        Serial.print("Distancia: "); Serial.print(reading.distanceCm, 1); Serial.println(" cm"); break;
    case UltrasonicSensor::ReadingStatus::Timeout: Serial.println("Distancia: invalida (timeout)"); break;
    case UltrasonicSensor::ReadingStatus::OutOfRange: Serial.println("Distancia: invalida (fuera de rango)"); break;
    default: Serial.println("Distancia: sin medicion"); break;
    }
    if (reading.status != UltrasonicSensor::ReadingStatus::NotMeasured) {
        Serial.print("Edad lectura (ms): "); Serial.println(static_cast<uint32_t>(millis() - reading.timestampMs));
    }
    Serial.print("Vehiculo detectado: ");
    switch (sensor.presence()) {
    case UltrasonicSensor::Presence::Present: Serial.println("SI"); break;
    case UltrasonicSensor::Presence::Absent: Serial.println("NO"); break;
    default: Serial.println("DESCONOCIDO"); break;
    }
}
void execute(SerialCommands::Command cmd) {
    using C = SerialCommands::Command;
    switch (cmd) {
    case C::Open: Serial.println("Comando recibido: OPEN"); barrier.open(); printBarrier(); break;
    case C::Close: Serial.println("Comando recibido: CLOSE"); barrier.close(); printBarrier(); break;
    case C::Status: printDistance(); printBarrier(); break;
    case C::Distance: printDistance(); break;
    case C::Help: Serial.println("Comandos: OPEN, CLOSE, STATUS, DISTANCE, HELP (terminar con CR o LF)"); break;
    case C::Invalid: Serial.println("Comando invalido o demasiado largo. Use HELP."); break;
    case C::None: break;
    }
}
}
void setup() {
    Serial.begin(Config::SERIAL_BAUD);
    sensor.begin();
    barrier.begin();
    lastSampleMs = millis();
    Serial.println("=== SmartPark - ESP32 / Fase 1 ===");
    Serial.println("Sistema iniciado. HC-SR04: pines configurados, funcionamiento no verificado.");
    printBarrier();
    execute(SerialCommands::Command::Help);
}
void loop() {
    // Presupuesto por vuelta para no monopolizar el bucle con trafico Serial.
    for (size_t i = 0; i < Config::SERIAL_BYTES_PER_LOOP && Serial.available() > 0; ++i)
        execute(commands.feed(static_cast<char>(Serial.read())));
    barrier.update();
    const uint32_t now = millis();
    if (static_cast<uint32_t>(now - lastSampleMs) >= Config::SENSOR_INTERVAL_MS) {
        lastSampleMs = now;
        sensor.measure();
        printDistance();
    }
}

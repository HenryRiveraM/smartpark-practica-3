#include "UltrasonicSensor.h"
#include "config.h"
void UltrasonicSensor::begin() {
    pinMode(TRIG_PIN, OUTPUT);
    digitalWrite(TRIG_PIN, LOW);
    pinMode(ECHO_PIN, INPUT);
    initialized_ = true;
    last_ = Measurement{};
    presence_ = Presence::Unknown;
}
const UltrasonicSensor::Measurement& UltrasonicSensor::measure() {
    if (!initialized_) return last_;
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(TRIG_LOW_US);
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(TRIG_HIGH_US);
    digitalWrite(TRIG_PIN, LOW);
    // Bloqueo acotado: hasta ECHO_TIMEOUT_US; nunca espera indefinidamente.
    const unsigned long duration = pulseIn(ECHO_PIN, HIGH, ECHO_TIMEOUT_US);
    last_.timestampMs = millis();
    last_.distanceCm = 0;
    last_.status = ReadingStatus::Timeout;
    if (duration != 0) {
        const float cm = duration * SOUND_CM_PER_US / 2.0f;
        last_.status = ReadingStatus::OutOfRange;
        if (cm >= MIN_DISTANCE_CM && cm <= MAX_DISTANCE_CM) {
            last_.distanceCm = cm;
            last_.status = ReadingStatus::Valid;
            if (cm <= VEHICLE_DETECTION_CM) presence_ = Presence::Present;
            else if (cm >= VEHICLE_DETECTION_CM + DETECTION_HYSTERESIS_CM)
                presence_ = Presence::Absent;
            else if (presence_ == Presence::Unknown) presence_ = Presence::Absent;
            return last_;
        }
    }
    // Un fallo invalida la presencia actual; no reutilizar una deteccion vieja.
    presence_ = Presence::Unknown;
    return last_;
}

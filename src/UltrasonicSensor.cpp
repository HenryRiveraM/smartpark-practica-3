#include "UltrasonicSensor.h"
#include "config.h"
void UltrasonicSensor::begin() {
    pinMode(Config::TRIG_PIN, OUTPUT);
    digitalWrite(Config::TRIG_PIN, LOW);
    pinMode(Config::ECHO_PIN, INPUT);
    initialized_ = true;
    last_ = Measurement{};
    presence_ = Presence::Unknown;
}
const UltrasonicSensor::Measurement& UltrasonicSensor::measure() {
    if (!initialized_) return last_;
    digitalWrite(Config::TRIG_PIN, LOW);
    delayMicroseconds(Config::TRIG_LOW_US);
    digitalWrite(Config::TRIG_PIN, HIGH);
    delayMicroseconds(Config::TRIG_HIGH_US);
    digitalWrite(Config::TRIG_PIN, LOW);
    // Bloqueo acotado: hasta ECHO_TIMEOUT_US; nunca espera indefinidamente.
    const unsigned long duration = pulseIn(Config::ECHO_PIN, HIGH, Config::ECHO_TIMEOUT_US);
    last_.timestampMs = millis();
    last_.distanceCm = 0;
    last_.status = ReadingStatus::Timeout;
    if (duration != 0) {
        const float cm = duration * Config::SOUND_CM_PER_US / 2.0f;
        last_.status = ReadingStatus::OutOfRange;
        if (cm >= Config::MIN_DISTANCE_CM && cm <= Config::MAX_DISTANCE_CM) {
            last_.distanceCm = cm;
            last_.status = ReadingStatus::Valid;
            if (cm <= Config::VEHICLE_DETECTION_CM) presence_ = Presence::Present;
            else if (cm >= Config::VEHICLE_DETECTION_CM + Config::DETECTION_HYSTERESIS_CM)
                presence_ = Presence::Absent;
            else if (presence_ == Presence::Unknown) presence_ = Presence::Absent;
            return last_;
        }
    }
    // Un fallo invalida la presencia actual; no reutilizar una deteccion vieja.
    presence_ = Presence::Unknown;
    return last_;
}

#pragma once
#include <Arduino.h>
class UltrasonicSensor {
public:
    enum class ReadingStatus { NotMeasured, Valid, Timeout, OutOfRange };
    enum class Presence { Unknown, Absent, Present };
    struct Measurement {
        ReadingStatus status = ReadingStatus::NotMeasured;
        float distanceCm = 0; // Solo utilizable cuando status == Valid.
        uint32_t timestampMs = 0;
    };
    void begin();
    const Measurement& measure();
    const Measurement& lastMeasurement() const { return last_; }
    Presence presence() const { return presence_; }
private:
    bool initialized_ = false;
    Measurement last_;
    Presence presence_ = Presence::Unknown;
};

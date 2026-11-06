#pragma once
#include <Arduino.h>
#include <ESP32Servo.h>
class BarrierServo {
public:
    enum class State { Closed, Open };
    bool begin();
    bool open();
    bool close();
    void update();
    bool initialized() const { return initialized_; }
    State commandedState() const { return commanded_; }
    bool moving() const { return moving_; }
    // Es una estimacion temporal; no existe realimentacion fisica.
    bool positionEstimated() const { return initialized_ && !moving_; }
private:
    bool command(State state);
    Servo servo_;
    bool initialized_ = false, moving_ = false;
    State commanded_ = State::Closed;
    uint32_t commandTime_ = 0;
};

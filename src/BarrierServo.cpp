#include "BarrierServo.h"
#include "config.h"
bool BarrierServo::begin() {
    if (initialized_) return true;
    servo_.setPeriodHertz(SERVO_FREQUENCY_HZ);
    servo_.attach(SERVO_PIN, SERVO_MIN_US, SERVO_MAX_US);
    initialized_ = servo_.attached();
    if (initialized_) {
        servo_.write(BARRIER_CLOSED_ANGLE);
        commanded_ = State::Closed;
        commandTime_ = millis();
        moving_ = true;
    }
    return initialized_;
}
bool BarrierServo::command(State state) {
    if (!initialized_ || state == commanded_) return false;
    servo_.write(state == State::Open ? BARRIER_OPEN_ANGLE : BARRIER_CLOSED_ANGLE);
    commanded_ = state;
    commandTime_ = millis();
    moving_ = true;
    return true;
}
bool BarrierServo::open() { return command(State::Open); }
bool BarrierServo::close() { return command(State::Closed); }
void BarrierServo::update() {
    if (moving_ && static_cast<uint32_t>(millis() - commandTime_) >= SERVO_TRAVEL_MS)
        moving_ = false;
}

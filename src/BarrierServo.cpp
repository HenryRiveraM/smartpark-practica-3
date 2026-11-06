#include "BarrierServo.h"
#include "config.h"
bool BarrierServo::begin() {
    if (initialized_) return true;
    servo_.setPeriodHertz(Config::SERVO_FREQUENCY_HZ);
    servo_.attach(Config::SERVO_PIN, Config::SERVO_MIN_US, Config::SERVO_MAX_US);
    initialized_ = servo_.attached();
    if (initialized_) {
        servo_.write(Config::BARRIER_CLOSED_ANGLE);
        commanded_ = State::Closed;
        commandTime_ = millis();
        moving_ = true;
    }
    return initialized_;
}
bool BarrierServo::command(State state) {
    if (!initialized_ || state == commanded_) return false;
    servo_.write(state == State::Open ? Config::BARRIER_OPEN_ANGLE : Config::BARRIER_CLOSED_ANGLE);
    commanded_ = state;
    commandTime_ = millis();
    moving_ = true;
    return true;
}
bool BarrierServo::open() { return command(State::Open); }
bool BarrierServo::close() { return command(State::Closed); }
void BarrierServo::update() {
    if (moving_ && static_cast<uint32_t>(millis() - commandTime_) >= Config::SERVO_TRAVEL_MS)
        moving_ = false;
}

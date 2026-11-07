#pragma once
#include "BarrierServo.h"
#include "UltrasonicSensor.h"
// Integracion local: no inicia red en las pruebas del loop.
class AwsIoTManager {
public:
    bool begin() { return true; }
    void tick(BarrierServo&, const UltrasonicSensor&) {}
    void noteSerialCommand(bool) {}
    void printStatus() {}
};

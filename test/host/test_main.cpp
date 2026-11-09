#include <cassert>
#include <cmath>
#include <iostream>
#include <limits>
#include "UltrasonicSensor.h"
#include "BarrierServo.h"
#include "SerialCommands.h"
void setup();
void loop();
int main() {
    using R=UltrasonicSensor::ReadingStatus;
    using P=UltrasonicSensor::Presence;
    UltrasonicSensor sensor;
    assert(sensor.measure().status==R::NotMeasured);
    sensor.begin();
    assert(Fake::modes[TRIG_PIN]==OUTPUT && Fake::modes[ECHO_PIN]==INPUT);
    assert(Fake::levels[TRIG_PIN]==LOW && sensor.presence()==P::Unknown);
    Fake::echo=700; // 12.005 cm
    assert(sensor.measure().status==R::Valid);
    assert(std::fabs(sensor.lastMeasurement().distanceCm-12.005f)<0.01f);
    assert(sensor.presence()==P::Present && Fake::timeout==ECHO_TIMEOUT_US);
    Fake::echo=960; sensor.measure(); assert(sensor.presence()==P::Present); // 16.46 cm
    Fake::echo=1200; sensor.measure(); assert(sensor.presence()==P::Absent); // 20.58 cm
    Fake::echo=960; sensor.measure(); assert(sensor.presence()==P::Absent);
    Fake::echo=0; assert(sensor.measure().status==R::Timeout && sensor.presence()==P::Unknown);
    Fake::echo=1; assert(sensor.measure().status==R::OutOfRange && sensor.presence()==P::Unknown);
    Fake::echo=25000; assert(sensor.measure().status==R::OutOfRange);
    Fake::echo=700; sensor.measure(); assert(sensor.presence()==P::Present);

    BarrierServo barrier;
    assert(!barrier.open() && !barrier.positionEstimated());
    Fake::attachSuccess=false; assert(!barrier.begin());
    Fake::attachSuccess=true; assert(barrier.begin() && barrier.moving());
    assert(Fake::pulseUs==500 && Fake::frequency==50);
    assert(Fake::servoPin==25 && Fake::minUs==500 && Fake::maxUs==2400);
    auto writes=Fake::writes; assert(!barrier.close() && Fake::writes==writes);
    Fake::now+=SERVO_TRAVEL_MS-1; barrier.update(); assert(barrier.moving());
    ++Fake::now; barrier.update(); assert(barrier.positionEstimated());
    assert(barrier.open() && Fake::pulseUs==1450);
    writes=Fake::writes; assert(!barrier.open() && Fake::writes==writes);
    assert(barrier.close() && barrier.commandedState()==BarrierServo::State::Closed);
    Fake::now=std::numeric_limits<uint32_t>::max()-100;
    barrier.open(); Fake::now+=SERVO_TRAVEL_MS; barrier.update();
    assert(barrier.positionEstimated());

    using C=SerialCommands::Command;
    SerialCommands parser;
    auto parse=[&](const std::string& s) { C last=C::None; for(char c:s) { auto r=parser.feed(c); if(r!=C::None) last=r; } return last; };
    assert(parse(" op")==C::None && parse("en \r\n")==C::Open);
    assert(parse("CLOSE\n")==C::Close && parse("STATUS\n")==C::Status);
    assert(parse("DISTANCE\n")==C::Distance && parse("help\n")==C::Help);
    assert(parse("INVALID\n")==C::Invalid && parse(" \n")==C::None);
    assert(parse(std::string(100,'x')+"OPEN\n")==C::Invalid);
    assert(parse("OPEN\n")==C::Open);

    Fake::now=0; setup();
    const auto triggerCount=Fake::triggers;
    Serial.output.clear(); Serial.inject("OPEN\n"); loop();
    assert(Fake::pulseUs==1450);
    assert(Fake::triggers==triggerCount); // No medicion antes del intervalo.
    Fake::now=500; Fake::echo=0; Serial.inject("CLOSE\nSTATUS\nDISTANCE\nHELP\n"); loop();
    assert(Fake::triggers==triggerCount+1 && Fake::pulseUs==500);
    assert(Serial.output.find("timeout")!=std::string::npos);
    // Sensor detecta, pero nunca abre la barrera.
    Fake::now=1000; Fake::echo=700; loop(); assert(Fake::pulseUs==500);
    Serial.inject(std::string(1000,'x')+"\nOPEN\n"); Fake::now=1500;
    loop(); assert(Serial.available()>0); // Presupuesto Serial respeta la tarea periodica.
    assert(Fake::triggers==triggerCount+3);
    while(Serial.available()) loop();
    assert(Fake::pulseUs==1450);
    Serial.inject("STATUS\n"); loop();
    assert(Serial.output.find("Barrera ordenada: ABIERTA")!=std::string::npos);
    std::cout << "PASS: sensor, histeresis, servo, parser e integracion del loop (simulados)\n";
}

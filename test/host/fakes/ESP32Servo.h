#pragma once
namespace Fake {
inline bool attachSuccess=true;
inline unsigned writes=0;
inline int angle=-1, frequency=0, servoPin=-1, minUs=0, maxUs=0;
}
class Servo {
    bool attached_=false;
public:
    void setPeriodHertz(int hz) { Fake::frequency=hz; }
    int attach(int pin,int low,int high) {
        Fake::servoPin=pin;Fake::minUs=low;Fake::maxUs=high;
        attached_=Fake::attachSuccess;return 0;
    }
    bool attached() { return attached_; }
    void write(int value) { Fake::angle=value; ++Fake::writes; }
};

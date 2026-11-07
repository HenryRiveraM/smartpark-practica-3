#pragma once
#include <cstdint>
#include <cstddef>
#include <string>
#include <deque>
#include <array>
#include <cstdio>
constexpr int LOW=0, HIGH=1, INPUT=1, OUTPUT=2;
namespace Fake {
inline uint32_t now=0;
inline unsigned long echo=0, timeout=0;
inline std::array<int,40> modes{}, levels{};
inline unsigned triggers=0;
}
inline uint32_t millis() { return Fake::now; }
inline void pinMode(int p,int m) { Fake::modes[p]=m; }
inline void digitalWrite(int p,int v) { Fake::levels[p]=v; if(v==HIGH) ++Fake::triggers; }
inline void delayMicroseconds(unsigned long) {}
inline unsigned long pulseIn(int,int,unsigned long timeout) {
    Fake::timeout=timeout;
    Fake::now += Fake::echo ? Fake::echo/1000 : timeout/1000;
    return Fake::echo;
}
struct FakeSerial {
    std::deque<char> input;
    std::string output;
    template<class... T> void printf(const char* f, T... args) { char b[1024]; std::snprintf(b,sizeof(b),f,args...); output+=b; }
    void begin(uint32_t) {}
    int available() { return static_cast<int>(input.size()); }
    int read() { char c=input.front();input.pop_front();return c; }
    void inject(const std::string& s) { for(char c:s) input.push_back(c); }
    void print(const char* s) { output+=s; }
    void print(float n,int) { output+=std::to_string(n); }
    void println(const char* s) { output+=s;output+='\n'; }
    void println(uint32_t n) { output+=std::to_string(n);output+='\n'; }
};
inline FakeSerial Serial;

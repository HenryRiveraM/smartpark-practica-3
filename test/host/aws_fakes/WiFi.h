#pragma once
constexpr int WIFI_STA=1, WL_CONNECTED=3;
struct FakeWiFi {
    int state=WL_CONNECTED;
    unsigned begins=0;
    int status() { return state; }
    void mode(int) {}
    void setAutoReconnect(bool) {}
    void disconnect(bool=false) { state=0; }
    void begin(const char*,const char*) { ++begins; }
};
inline FakeWiFi WiFi;
inline void configTime(int,int,const char*,const char*) {}

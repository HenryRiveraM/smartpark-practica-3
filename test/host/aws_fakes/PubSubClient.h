#pragma once
#include <functional>
#include <vector>
#include <string>
#include "WiFiClientSecure.h"
class PubSubClient {
public:
    bool online=false, connectOK=true, publishOK=true;
    unsigned connects=0;
    std::vector<std::string> topics, bodies, subscriptions;
    explicit PubSubClient(WiFiClientSecure&) {}
    bool connected() { return online; }
    void disconnect() { online=false; }
    void setServer(const char*,unsigned) {}
    bool setBufferSize(unsigned) { return true; }
    void setKeepAlive(unsigned) {}
    void setSocketTimeout(unsigned) {}
    template<class T> void setCallback(T) {}
    bool connect(const char*) { ++connects; online=connectOK; return online; }
    bool subscribe(const char* t,int) { subscriptions.emplace_back(t); return true; }
    bool publish(const char* t,const char* b) { topics.emplace_back(t); bodies.emplace_back(b); return publishOK; }
    void loop() {}
    int state() { return online?0:-1; }
};

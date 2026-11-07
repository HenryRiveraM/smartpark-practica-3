#pragma once
class WiFiClientSecure {
public:
    void setCACert(const char*) {}
    void setCertificate(const char*) {}
    void setPrivateKey(const char*) {}
    void setHandshakeTimeout(unsigned) {}
    void setTimeout(unsigned) {}
    void stop() {}
};

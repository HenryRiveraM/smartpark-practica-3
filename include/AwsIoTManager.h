#pragma once
#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <Preferences.h>
#include "BarrierServo.h"
#include "UltrasonicSensor.h"
#include "ShadowBudget.h"

// Solo tick() toca hardware. La tarea de red es la unica propietaria de MQTT/NVS.
class AwsIoTManager {
public:
    bool begin();
    void tick(BarrierServo& barrier, const UltrasonicSensor& sensor);
    void printStatus();
    void noteSerialCommand(bool open);
private:
    friend struct AwsIoTManagerTest;
    struct Snapshot {
        float distance = 0;
        bool valid = false, ready = false, open = false;
        int presence = -1;
        uint32_t sample = 0, applied = 0, serial = 0;
        bool serialOpen = false;
    };
    struct Command { bool open; uint32_t sequence; };
    uint32_t mainApplied_ = 0, mainSerial_ = 0;
    bool mainSerialOpen_ = false;
    uint32_t desiredSequence_ = 0, seenSerial_ = 0;
    struct Status {
        uint32_t counts[4] = {}, reconnects = 0, skipped = 0, accepted = 0, rejected = 0;
        uint32_t lastPublish = 0, connectedMs = 0, day = 0;
        bool wifi = false, mqtt = false, budgetOK = false, demoEnded = false, stopped = false;
        char lastCommand[24] = "ninguno";
    };
    QueueHandle_t snapshots_ = nullptr, commands_ = nullptr, statuses_ = nullptr;
    TaskHandle_t task_ = nullptr;
    WiFiClientSecure tls_;
    PubSubClient mqtt_{tls_};
    Preferences prefs_;
    ShadowBudget budget_;
    Snapshot current_, confirmed_, sent_;
    Status status_;
    bool storageOK_ = false, timeReady_ = false, demoEnded_ = false;
    bool synced_ = false, haveConfirmed_ = false, inflight_ = false, getPending_ = false;
    bool controlPending_ = false, rejectedBlocked_ = false;
    uint32_t lastSample_ = 0, stableCount_ = 0;
    int candidate_ = -1, stablePresence_ = -1;
    uint32_t nextAttempt_ = 0, retryDelay_ = 0, attempts_ = 0, connections_ = 0;
    uint32_t lastPublish_ = 0, lastReport_ = 0;
    uint32_t requestAt_ = 0, requestAttempts_ = 0, tokenSequence_ = 0, version_ = 0;
    uint32_t lastSkip_ = 0;
    bool limitLogged_ = false;
    uint32_t connectedMs_ = 0, clockMs_ = 0, ntpAt_ = 0;
    bool ntpStarted_ = false;
    char token_[48] = {};
    static void taskEntry(void* arg);
    void run();
    void step();
    void receive(char* topic, uint8_t* payload, unsigned int length);
    void connectStep(uint32_t now);
    void failedAttempt(uint32_t now);
    void disconnect();
    bool reserve(ShadowBudget::Kind kind);
    bool refreshDay();
    bool loadBudget();
    void requestShadow();
    void report(ShadowBudget::Kind kind);
    void applyDesired(const char* value);
    void updateStatus();
};

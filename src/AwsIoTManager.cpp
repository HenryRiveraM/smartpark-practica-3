#include "AwsIoTManager.h"
#include "config.h"
#include "secrets.h"
#include <WiFi.h>
#include <ArduinoJson.h>
#include <esp_system.h>
#include <time.h>
#include <math.h>
#include <string.h>

bool AwsIoTManager::begin() {
    snapshots_ = xQueueCreate(1, sizeof(Snapshot));
    commands_ = xQueueCreate(1, sizeof(Command));
    statuses_ = xQueueCreate(1, sizeof(Status));
    if (!snapshots_ || !commands_ || !statuses_) return false;
    return xTaskCreate(taskEntry, "smartpark-aws", 12288, this, 1, &task_) == pdPASS;
}
void AwsIoTManager::tick(BarrierServo& barrier, const UltrasonicSensor& sensor) {
    if (!task_) return;
    Command cmd;
    if (xQueueReceive(commands_, &cmd, 0) == pdTRUE) {
        if (cmd.open) barrier.open(); else barrier.close();
        mainApplied_ = cmd.sequence;
    }
    Snapshot s;
    const auto& m = sensor.lastMeasurement();
    s.sample = m.timestampMs;
    s.valid = m.status == UltrasonicSensor::ReadingStatus::Valid;
    s.distance = m.distanceCm;
    s.presence = sensor.presence() == UltrasonicSensor::Presence::Unknown ? -1 :
                 (sensor.presence() == UltrasonicSensor::Presence::Present ? 1 : 0);
    s.open = barrier.commandedState() == BarrierServo::State::Open;
    s.ready = barrier.positionEstimated();
    s.applied = mainApplied_; s.serial = mainSerial_; s.serialOpen = mainSerialOpen_;
    xQueueOverwrite(snapshots_, &s);
}
void AwsIoTManager::noteSerialCommand(bool open) { ++mainSerial_; mainSerialOpen_ = open; }
void AwsIoTManager::printStatus() {
    Status s;
    if (!statuses_ || xQueuePeek(statuses_, &s, 0) != pdTRUE) {
        Serial.println("AWS: tarea no iniciada o inicializando; control local disponible"); return;
    }
    Serial.printf("AWS WiFi=%s MQTT/TLS=%s ultimo=%s reconexiones=%lu\n",
        s.wifi?"conectado":"desconectado", s.mqtt?"conectado":"desconectado",
        s.lastCommand, (unsigned long)s.reconnects);
    Serial.printf("Shadow UPDATE=%lu solicitudesTotales=%lu: periodicas=%lu sensor=%lu control=%lu GET=%lu; accepted=%lu rejected=%lu omitidas=%lu\n",
        (unsigned long)(s.counts[0]+s.counts[1]+s.counts[2]),
        (unsigned long)(s.counts[0]+s.counts[1]+s.counts[2]+s.counts[3]),
        (unsigned long)s.counts[0], (unsigned long)s.counts[1], (unsigned long)s.counts[2],
        (unsigned long)s.counts[3], (unsigned long)s.accepted, (unsigned long)s.rejected, (unsigned long)s.skipped);
    Serial.printf("Diagnostico NVS=%s horaUTC=%s recuperacion=%s MQTTstate=%d intentos=%lu siguiente=%lu ms\n",
        s.storage?"OK":"ERROR", s.time?"OK":"INVALIDA", s.recoveryOK?"disponible":"bloqueada",
        s.mqttState, (unsigned long)s.attempts, (unsigned long)s.retryIn);
    Serial.printf("Presupuesto ordinario=%s diaUTC=%lu; ultima publicacion hace=%lu ms (0 si ninguna); demo=%s conectadoAcumulado=%lu ms; reintentos=%s\n",
        s.budgetOK?"disponible":"agotado/sin hora/NVS", (unsigned long)s.day,
        (unsigned long)(s.lastPublish ? millis()-s.lastPublish : 0),
        s.demoEnded?"finalizada":"activa", (unsigned long)s.connectedMs, s.stopped?"suspendidos":"habilitados");
}
void AwsIoTManager::taskEntry(void* arg) { static_cast<AwsIoTManager*>(arg)->run(); }
bool AwsIoTManager::loadBudget() {
    storageOK_ = prefs_.begin("smartpark-aws", false);
    if (storageOK_ && prefs_.isKey("budget")) {
        ShadowBudgetRecord r;
        storageOK_ = prefs_.getBytesLength("budget") == sizeof(r) &&
            prefs_.getBytes("budget", &r, sizeof(r)) == sizeof(r) && r.magic == budget_.record.magic;
        if (storageOK_) {
            budget_.record = r;
            uint64_t total = 0;
            for (auto count : r.counts) total += count;
            storageOK_ = r.day > 0 && total <= AWS_MAX_SHADOW_UPDATES_PER_DAY;
        }
    }
    return storageOK_;
}
void AwsIoTManager::run() {
    if (!loadBudget()) Serial.println("AWS: NVS invalida; envios bloqueados (no se repone presupuesto)");
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(false);
    tls_.setCACert(AWS_ROOT_CA);
    tls_.setCertificate(AWS_DEVICE_CERT);
    tls_.setPrivateKey(AWS_PRIVATE_KEY);
    tls_.setHandshakeTimeout(5);
    tls_.setTimeout(2); // WiFiClientSecure expresa este valor en segundos.
    mqtt_.setServer(AWS_IOT_ENDPOINT, MQTT_PORT);
    if (!mqtt_.setBufferSize(MQTT_BUFFER_SIZE)) {
        Serial.println("AWS: sin memoria MQTT, red suspendida");
        attempts_ = AWS_MAX_CONNECTION_ATTEMPTS;
    }
    mqtt_.setKeepAlive(120); // PING de protocolo, sin heartbeat de aplicacion.
    mqtt_.setSocketTimeout(2);
    mqtt_.setCallback([this](char* t, uint8_t* p, unsigned int n) { receive(t,p,n); });
    retryDelay_ = WIFI_RETRY_INTERVAL_MS;
    clockMs_ = millis();
    for (;;) { step(); vTaskDelay(pdMS_TO_TICKS(20)); }
}
bool AwsIoTManager::refreshDay() {
    const time_t epoch = time(nullptr);
    if (!storageOK_ || !timeReady_ || epoch < AWS_MIN_VALID_EPOCH) return false;
    const uint32_t day = static_cast<uint32_t>(epoch/86400);
    if (day < budget_.record.day) return false; // Retroceso temporal: cerrar presupuesto.
    if (budget_.advance(day)) {
        storageOK_ = prefs_.putBytes("budget", &budget_.record, sizeof(budget_.record)) == sizeof(budget_.record);
    }
    return storageOK_;
}
bool AwsIoTManager::reserve(ShadowBudget::Kind kind) {
    if (!refreshDay() || !budget_.allows(kind, AWS_MAX_SHADOW_UPDATES_PER_DAY, AWS_RESERVED_CONTROL_UPDATES)) return false;
    ++budget_.record.counts[kind];
    // Cuenta intentos incluso si TCP falla: nunca devolver una reserva incierta.
    storageOK_ = prefs_.putBytes("budget", &budget_.record, sizeof(budget_.record)) == sizeof(budget_.record);
    return storageOK_;
}
void AwsIoTManager::disconnect() {
    mqtt_.disconnect(); tls_.stop();
    synced_ = false; inflight_ = false; getPending_ = false;
}
void AwsIoTManager::failedAttempt(uint32_t now) {
    const int mqttState = mqtt_.state();
    disconnect(); ++attempts_;
    const uint32_t jitter = esp_random() % 1000;
    const uint32_t wait = retryDelay_ > AWS_RETRY_MAX_MS-jitter ? AWS_RETRY_MAX_MS : retryDelay_+jitter;
    nextAttempt_ = now + wait;
    retryDelay_ = retryDelay_ >= AWS_RETRY_MAX_MS/2 ? AWS_RETRY_MAX_MS : retryDelay_*2;
    Serial.printf("AWS: intento fallido %lu/%u; siguiente en %lu ms; MQTT=%d\n",
        (unsigned long)attempts_, AWS_MAX_CONNECTION_ATTEMPTS,
        (unsigned long)wait, mqttState);
}
void AwsIoTManager::connectStep(uint32_t now) {
    if (demoEnded_ || attempts_ >= AWS_MAX_CONNECTION_ATTEMPTS || !storageOK_) return;
    if (static_cast<int32_t>(now-nextAttempt_) < 0) return;
    if (WiFi.status() != WL_CONNECTED) {
        // Una llamada por ventana; WiFi.begin no espera asociacion.
        WiFi.disconnect(); WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
        ++attempts_;
        const uint32_t jitter = esp_random()%1000;
        nextAttempt_ = now + (retryDelay_ > AWS_RETRY_MAX_MS-jitter ? AWS_RETRY_MAX_MS : retryDelay_+jitter);
        retryDelay_ = retryDelay_ >= AWS_RETRY_MAX_MS/2 ? AWS_RETRY_MAX_MS : retryDelay_*2;
        Serial.printf("AWS WiFi: intento %lu/%u\n", (unsigned long)attempts_, AWS_MAX_CONNECTION_ATTEMPTS);
        return;
    }
    if (!ntpStarted_) {
        configTime(0, 0, "pool.ntp.org", "time.cloudflare.com");
        ntpStarted_ = true; ntpAt_ = now;
        Serial.println("AWS WiFi conectado; esperando NTP");
    }
    if (!timeReady_) {
        if (time(nullptr) >= AWS_MIN_VALID_EPOCH) timeReady_ = true;
        else {
            if (now-ntpAt_ >= AWS_NTP_TIMEOUT_MS) {
                Serial.println("AWS: NTP sin hora valida; reintento con backoff");
                ntpStarted_ = false; failedAttempt(now);
            }
            return;
        }
    }
    if (!refreshDay() || !budget_.allows(ShadowBudget::Recovery, AWS_MAX_SHADOW_UPDATES_PER_DAY, AWS_RESERVED_CONTROL_UPDATES)) return;
    Serial.println("AWS: conectando MQTT con TLS X.509 verificado");
    if (!mqtt_.connect(THING_NAME)) { failedAttempt(millis()); return; }
    const char* topics[] = {TOPIC_SHADOW_DELTA, TOPIC_SHADOW_GET_ACCEPTED,
        TOPIC_SHADOW_GET_REJECTED, TOPIC_SHADOW_UPDATE_ACCEPTED, TOPIC_SHADOW_UPDATE_REJECTED};
    for (const char* topic : topics) {
        if (!mqtt_.subscribe(topic, 1)) { failedAttempt(millis()); return; }
    }
    if (connections_++) ++status_.reconnects;
    // Solo una sincronizacion GET valida restablece los fallos consecutivos.
    ++attempts_; retryDelay_ = MQTT_RETRY_INTERVAL_MS;
    version_ = 0; requestAttempts_ = 0; rejectedBlocked_ = false;
    Serial.println("AWS MQTT/TLS conectado; suscripciones enviadas; GET unico");
    requestShadow();
}
void AwsIoTManager::requestShadow() {
    if (!mqtt_.connected() || !reserve(ShadowBudget::Recovery)) return;
    snprintf(token_, sizeof(token_), "%08lx-%lu", (unsigned long)esp_random(), (unsigned long)++tokenSequence_);
    char body[96]; snprintf(body, sizeof(body), "{\"clientToken\":\"%s\"}", token_);
    getPending_ = true; requestAt_ = millis(); lastPublish_ = requestAt_;
    if (!mqtt_.publish(TOPIC_SHADOW_GET, body)) failedAttempt(millis());
}
void AwsIoTManager::applyDesired(const char* value) {
    if (!value) return;
    if (strcmp(value,"abierta") && strcmp(value,"cerrada")) {
        Serial.println("AWS: desired.barrera invalida, ignorada"); return;
    }
    bool open = !strcmp(value,"abierta");
    snprintf(status_.lastCommand, sizeof(status_.lastCommand), "AWS %s", value);
    Serial.printf("AWS comando recibido: %s\n", value);
    // Si ya esta ejecutado y confirmado, no mover ni publicar.
    if (!controlPending_ && current_.applied >= desiredSequence_ && current_.ready && current_.open == open && haveConfirmed_ && confirmed_.ready && confirmed_.open == open) return;
    controlPending_ = true;
    Command cmd{open, ++desiredSequence_};
    xQueueOverwrite(commands_, &cmd);
}
void AwsIoTManager::receive(char* topic, uint8_t* payload, unsigned int length) {
    StaticJsonDocument<4096> doc;
    if (deserializeJson(doc, payload, length)) { Serial.println("AWS: JSON invalido/excede buffer; se esperara timeout si corresponde"); return; }
    const char* receivedToken = doc["clientToken"] | "";
    const bool ours = !strcmp(receivedToken, token_);
    if (!strcmp(topic, TOPIC_SHADOW_UPDATE_ACCEPTED)) {
        if (!inflight_ || !ours) return;
        inflight_ = false; ++status_.accepted;
        confirmed_ = sent_; haveConfirmed_ = true;
        requestAttempts_ = 0;
        if (current_.open == confirmed_.open && current_.applied >= desiredSequence_) controlPending_ = false;
        return;
    }
    if (!strcmp(topic, TOPIC_SHADOW_UPDATE_REJECTED)) {
        if (!inflight_ || !ours) return;
        inflight_ = false; ++status_.rejected;
        rejectedBlocked_ = true; // No martillar AWS con un documento/politica erroneos.
        Serial.printf("AWS: UPDATE rechazado codigo=%d; informes suspendidos hasta reconectar\n", doc["code"].as<int>());
        return;
    }
    if (!strcmp(topic, TOPIC_SHADOW_GET_REJECTED)) {
        if (!getPending_ || !ours) return;
        getPending_ = false; ++status_.rejected;
        if (doc["code"].as<int>() == 404) { synced_ = true; haveConfirmed_ = false; attempts_ = 0; }
        else { rejectedBlocked_ = true; Serial.println("AWS GET rechazado; informes suspendidos"); }
        return;
    }
    bool get = !strcmp(topic, TOPIC_SHADOW_GET_ACCEPTED);
    if (!get && strcmp(topic, TOPIC_SHADOW_DELTA)) return;
    if (get && (!getPending_ || !ours)) return;
    const uint32_t version = doc["version"] | 0U;
    if (get) {
        getPending_ = false; synced_ = true; attempts_ = 0;
        // Un delta mas reciente puede haberse procesado antes del GET.
        if (version < version_) return;
        JsonObject r = doc["state"]["reported"];
        const char* b = r["barrera"] | "";
        confirmed_ = Snapshot{};
        confirmed_.ready = !strcmp(b,"abierta") || !strcmp(b,"cerrada");
        confirmed_.open = !strcmp(b,"abierta");
        confirmed_.valid = r["distancia_cm"].is<float>();
        confirmed_.distance = r["distancia_cm"] | 0.0f;
        confirmed_.presence = r["vehiculo_detectado"].is<bool>() ? (r["vehiculo_detectado"].as<bool>()?1:0) : -1;
        haveConfirmed_ = true;
        version_ = version;
        applyDesired(doc["state"]["desired"]["barrera"] | static_cast<const char*>(nullptr));
    } else {
        if (version <= version_) return;
        version_ = version;
        applyDesired(doc["state"]["barrera"] | static_cast<const char*>(nullptr));
    }
}
void AwsIoTManager::report(ShadowBudget::Kind kind) {
    if (!reserve(kind)) return;
    StaticJsonDocument<512> doc;
    snprintf(token_, sizeof(token_), "%08lx-%lu", (unsigned long)esp_random(), (unsigned long)++tokenSequence_);
    doc["clientToken"] = token_;
    JsonObject r = doc.createNestedObject("state").createNestedObject("reported");
    r["barrera_posicion_estimada"] = true; // SG90 sin realimentacion fisica.
    r["barrera"] = current_.open ? "abierta" : "cerrada";
    // null borra datos viejos: un timeout nunca se presenta como distancia/presencia valida.
    if (current_.valid) r["distancia_cm"] = roundf(current_.distance*10)/10; else r["distancia_cm"] = nullptr;
    const int reportedPresence = current_.valid ? stablePresence_ : -1;
    if (reportedPresence >= 0) r["vehiculo_detectado"] = reportedPresence == 1; else r["vehiculo_detectado"] = nullptr;
    char body[512]; serializeJson(doc, body, sizeof(body));
    sent_ = current_; sent_.presence = reportedPresence;
    inflightKind_ = kind;
    inflight_ = true; requestAt_ = millis(); lastPublish_ = requestAt_;
    lastReport_ = requestAt_;
    ++requestAttempts_;
    Serial.printf("AWS UPDATE clase=%u intento=%lu\n", static_cast<unsigned>(kind), (unsigned long)requestAttempts_);
    if (!mqtt_.publish(TOPIC_SHADOW_UPDATE, body)) failedAttempt(millis());
}
void AwsIoTManager::step() {
    uint32_t now = millis();
    const uint32_t elapsed = now-clockMs_; clockMs_ = now;
    if (mqtt_.connected()) connectedMs_ += elapsed;
    if (AWS_DEMO_MAX_CONNECTED_MS && connectedMs_ >= AWS_DEMO_MAX_CONNECTED_MS && !demoEnded_) {
        demoEnded_ = true; disconnect(); WiFi.disconnect(true);
        Serial.println("AWS: demo finalizada; no reconectar hasta reiniciar. Sensor y servo locales activos.");
    }
    Snapshot s;
    bool sampled = false;
    if (xQueueReceive(snapshots_, &s, 0) == pdTRUE) {
        current_ = s;
        if (s.serial != seenSerial_) {
            seenSerial_ = s.serial;
            snprintf(status_.lastCommand,sizeof(status_.lastCommand),"Serial %s",s.serialOpen?"OPEN":"CLOSE");
        }
        if (s.sample != lastSample_) {
            // Durante TLS pueden perderse muestras intermedias en la cola de ultima lectura.
            // No declarar estabilidad acumulando observaciones separadas por una reconexion.
            if (lastSample_ && s.sample-lastSample_ > SENSOR_INTERVAL_MS+ECHO_TIMEOUT_US/1000+100) {
                stableCount_ = 0; candidate_ = -2;
            }
            lastSample_ = s.sample; sampled = true;
            if (candidate_ == s.presence) { if (stableCount_ < AWS_PRESENCE_STABLE_SAMPLES) ++stableCount_; }
            else { candidate_ = s.presence; stableCount_ = 1; }
            if (stableCount_ >= AWS_PRESENCE_STABLE_SAMPLES) stablePresence_ = candidate_;
        }
    }
    if (!demoEnded_) {
        if (!mqtt_.connected()) {
            if (synced_ || inflight_ || getPending_) {
                Serial.println("AWS: conexion perdida; backoff"); failedAttempt(now);
            }
            connectStep(now);
        } else {
            mqtt_.loop(); now = millis();
            if (getPending_ && now-requestAt_ >= AWS_SHADOW_RESPONSE_TIMEOUT_MS) {
                Serial.println("AWS GET sin respuesta; resincronizacion con backoff"); failedAttempt(now);
            }
            // Un cambio ejecutado del servo no espera el acuse de un informe viejo.
            // La reserva anterior queda consumida; su token tardio sera ignorado.
            if (inflight_ && current_.ready && current_.applied >= desiredSequence_ && current_.open != sent_.open) {
                inflight_ = false; controlPending_ = true; requestAttempts_ = 0;
            }
            // Una presencia confirmada desplaza un reporte anterior sin esperar su timeout.
            if (inflight_ && inflightKind_ != ShadowBudget::Control && !controlPending_ && stableCount_ >= AWS_PRESENCE_STABLE_SAMPLES &&
                stablePresence_ != sent_.presence) inflight_ = false;
            if (inflight_ && now-requestAt_ >= AWS_SHADOW_RESPONSE_TIMEOUT_MS) {
                inflight_ = false;
                if (requestAttempts_ >= AWS_MAX_REQUEST_ATTEMPTS) {
                    rejectedBlocked_ = true;
                    Serial.println("AWS: sin confirmacion tras limite de intentos; informes suspendidos");
                }
            }
            const bool ready = current_.ready && current_.applied >= desiredSequence_;
            if (mqtt_.connected() && synced_ && !inflight_ && !rejectedBlocked_ && ready) {
                bool control = controlPending_ || !haveConfirmed_ || !confirmed_.ready || current_.open != confirmed_.open;
                bool presence = stableCount_ >= AWS_PRESENCE_STABLE_SAMPLES &&
                    stablePresence_ != confirmed_.presence;
                bool sensor = presence || current_.valid != confirmed_.valid ||
                    (current_.valid && fabsf(current_.distance-confirmed_.distance) >= AWS_DISTANCE_CHANGE_THRESHOLD_CM);
                bool periodic = now-lastReport_ >= AWS_REPORT_INTERVAL_MS;
                if (!control && !sensor && !periodic && sampled) ++status_.skipped;
                if (control || sensor || periodic) {
                    ShadowBudget::Kind kind = control ? ShadowBudget::Control : (sensor ? ShadowBudget::Sensor : ShadowBudget::Periodic);
                    bool interval = control || presence || now-lastPublish_ >= AWS_MIN_PUBLISH_INTERVAL_MS;
                    bool allowed = refreshDay() && budget_.allows(kind, AWS_MAX_SHADOW_UPDATES_PER_DAY,AWS_RESERVED_CONTROL_UPDATES);
                    if (!allowed && !limitLogged_) {
                        Serial.println("AWS: limite local/hora/NVS impide envios; lecturas y comandos siguen activos");
                        limitLogged_ = true;
                    }
                    if (allowed) limitLogged_ = false;
                    if (interval && allowed) report(kind);
                    else if (now-lastSkip_ >= 1000) {
                        // Contador de decisiones omitidas, como maximo una por segundo.
                        ++status_.skipped; lastSkip_ = now;
                    }
                }
            }
        }
    }
    updateStatus();
}
void AwsIoTManager::updateStatus() {
    status_.time = timeReady_ && time(nullptr) >= AWS_MIN_VALID_EPOCH &&
        static_cast<uint32_t>(time(nullptr)/86400) >= budget_.record.day;
    status_.recoveryOK = refreshDay() && budget_.allows(ShadowBudget::Recovery,
        AWS_MAX_SHADOW_UPDATES_PER_DAY, AWS_RESERVED_CONTROL_UPDATES);
    status_.storage = storageOK_;
    status_.mqttState = mqtt_.state(); status_.attempts = attempts_;
    status_.retryIn = static_cast<int32_t>(nextAttempt_-millis()) > 0 ? nextAttempt_-millis() : 0;
    status_.wifi = WiFi.status() == WL_CONNECTED; status_.mqtt = mqtt_.connected();
    for (unsigned i=0;i<4;++i) status_.counts[i] = budget_.record.counts[i];
    status_.budgetOK = refreshDay() && budget_.allows(ShadowBudget::Periodic,AWS_MAX_SHADOW_UPDATES_PER_DAY,AWS_RESERVED_CONTROL_UPDATES);
    status_.day = budget_.record.day;
    status_.lastPublish = lastPublish_; status_.connectedMs = connectedMs_;
    status_.demoEnded = demoEnded_; status_.stopped = attempts_ >= AWS_MAX_CONNECTION_ATTEMPTS || rejectedBlocked_ || !storageOK_;
    xQueueOverwrite(statuses_, &status_);
}

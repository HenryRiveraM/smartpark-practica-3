#include "AwsIoTManager.h"
#include "config.h"
#include <WiFi.h>
#include <cassert>
#include <iostream>
#include <ctime>
#include <cstring>
struct AwsIoTManagerTest {
    static void receive(AwsIoTManager& a,const char* topic,const std::string& body) {
        a.receive(const_cast<char*>(topic),reinterpret_cast<uint8_t*>(const_cast<char*>(body.data())),body.size());
    }
    static void ack(AwsIoTManager& a) { receive(a,TOPIC_SHADOW_UPDATE_ACCEPTED,std::string("{\"clientToken\":\"")+a.token_+"\"}"); }
    static void init(AwsIoTManager& a) {
        assert(a.begin()); a.storageOK_=true; a.timeReady_=true;
        a.retryDelay_=WIFI_RETRY_INTERVAL_MS;
        assert(a.refreshDay()); WiFi.state=WL_CONNECTED;
    }
    static void run() {
        ShadowBudget b;
        assert(b.advance(100)); b.record.counts[ShadowBudget::Periodic]=170;
        assert(!b.allows(ShadowBudget::Periodic,200,30));
        assert(!b.allows(ShadowBudget::Recovery,200,30));
        assert(b.allows(ShadowBudget::Control,200,30));
        assert(!b.advance(99) && b.total()==170);
        assert(!b.advance(100) && b.total()==170);
        b.record.counts[ShadowBudget::Control]=30;
        assert(!b.allows(ShadowBudget::Control,200,30));
        assert(b.advance(101) && b.total()==0);

        Fake::now=10000;
        AwsIoTManager a; init(a);
        a.connectStep(Fake::now);
        assert(a.mqtt_.connects==1 && a.mqtt_.subscriptions.size()==5);
        assert(a.mqtt_.topics.size()==1 && a.mqtt_.topics[0]==TOPIC_SHADOW_GET);
        a.step(); a.step(); assert(a.mqtt_.topics.size()==1); // GET unico
        auto getToken=std::string(a.token_);
        receive(a,TOPIC_SHADOW_GET_ACCEPTED,"{\"clientToken\":\""+getToken+"\",\"version\":1,\"state\":{\"reported\":{\"barrera\":\"cerrada\",\"distancia_cm\":20,\"vehiculo_detectado\":false}}}");
        assert(a.synced_ && a.haveConfirmed_);
        a.current_.ready=true; a.current_.open=false; a.current_.valid=true; a.current_.distance=20;
        a.stablePresence_=0;
        a.step(); assert(a.mqtt_.topics.size()==1);
        receive(a,TOPIC_SHADOW_DELTA,"{\"version\":2,\"state\":{\"barrera\":\"abierta\"}}");
        AwsIoTManager::Command cmd;
        assert(xQueueReceive(a.commands_,&cmd,0) && cmd.open);
        a.step(); assert(a.mqtt_.topics.size()==1); // Esperar ejecucion, no confirmar anticipadamente
        a.current_.applied=cmd.sequence; a.current_.open=true; a.current_.ready=false;
        a.step(); assert(a.mqtt_.topics.size()==1);
        a.current_.ready=true; a.step(); assert(a.inflight_ && a.mqtt_.topics.size()==2);
        assert(a.mqtt_.bodies.back().find("desired")==std::string::npos);
        ack(a); assert(a.confirmed_.open && !a.inflight_);
        receive(a,TOPIC_SHADOW_DELTA,"{\"version\":3,\"state\":{\"barrera\":\"abierta\"}}");
        a.step(); assert(a.mqtt_.topics.size()==2 && !a.commands_->full);
        receive(a,TOPIC_SHADOW_DELTA,"{\"version\":2,\"state\":{\"barrera\":\"cerrada\"}}");
        assert(!a.commands_->full); // version atrasada
        receive(a,TOPIC_SHADOW_DELTA,"{\"version\":4,\"state\":{\"barrera\":\"cerrada\"}}");
        assert(xQueueReceive(a.commands_,&cmd,0) && !cmd.open);
        a.current_.applied=cmd.sequence; a.current_.open=false; a.step(); ack(a);
        assert(!a.confirmed_.open && a.budget_.record.counts[ShadowBudget::Control]==2);
        Fake::now+=AWS_MIN_PUBLISH_INTERVAL_MS;
        a.current_.distance=22; a.step(); assert(!a.inflight_);
        a.current_.distance=30; a.step(); assert(a.inflight_); ack(a);
        assert(a.budget_.record.counts[ShadowBudget::Sensor]==1);
        Fake::now+=AWS_MIN_PUBLISH_INTERVAL_MS;
        a.stablePresence_=1; a.step(); assert(a.inflight_); ack(a);
        Fake::now+=AWS_REPORT_INTERVAL_MS;
        a.step(); assert(a.inflight_); ack(a);
        assert(a.budget_.record.counts[ShadowBudget::Periodic]==1);
        auto persisted=Preferences::disk;
        ShadowBudgetRecord restored; std::memcpy(&restored,persisted.data(),sizeof(restored));
        assert(restored.counts[ShadowBudget::Control]==2 && restored.counts[ShadowBudget::Recovery]==1);
        AwsIoTManager restarted;
        assert(restarted.loadBudget());
        assert(restarted.budget_.total()==a.budget_.total());
        assert(restarted.budget_.record.day==a.budget_.record.day);
        Preferences::disk[0]=0;
        AwsIoTManager corrupt;
        assert(!corrupt.loadBudget());
        Preferences::disk=persisted;
        a.budget_.record.counts[ShadowBudget::Periodic]=170;
        assert(!a.reserve(ShadowBudget::Sensor));
        assert(a.reserve(ShadowBudget::Control));
        Preferences::writable=false;
        assert(!a.reserve(ShadowBudget::Control) && !a.storageOK_);
        Preferences::writable=true; a.storageOK_=true;
        a.budget_.record.counts[ShadowBudget::Periodic]=0;
        a.mqtt_.online=false; a.step(); auto connects=a.mqtt_.connects;
        a.step(); assert(a.mqtt_.connects==connects); // backoff
        Fake::now=a.nextAttempt_; a.step(); assert(a.mqtt_.connects==connects+1 && a.getPending_);
        // Desired pendiente en el GET tras reconectar; no repetir GET en loop.
        auto pendingToken=std::string(a.token_);
        receive(a,TOPIC_SHADOW_GET_ACCEPTED,"{\"clientToken\":\""+pendingToken+"\",\"version\":10,\"state\":{\"desired\":{\"barrera\":\"abierta\"},\"reported\":{\"barrera\":\"cerrada\"}}}");
        assert(a.commands_->full);
        a.connectedMs_=AWS_DEMO_MAX_CONNECTED_MS; a.step();
        assert(a.demoEnded_ && !a.mqtt_.online);
        Fake::now+=AWS_RETRY_MAX_MS; a.step(); assert(a.mqtt_.connects==connects+1);
        // Debounce por muestras, nunca por numero de iteraciones de loop.
        AwsIoTManager stable; init(stable);
        stable.mqtt_.online=true; stable.synced_=true; stable.haveConfirmed_=true;
        stable.confirmed_.ready=true; stable.confirmed_.valid=true; stable.confirmed_.distance=20;
        stable.confirmed_.presence=0; stable.stablePresence_=0;
        stable.lastReport_=Fake::now; stable.lastPublish_=Fake::now;
        AwsIoTManager::Snapshot snapshot;
        snapshot.ready=true; snapshot.valid=true; snapshot.distance=20; snapshot.presence=1;
        for (unsigned i=1;i<=AWS_PRESENCE_STABLE_SAMPLES;++i) {
            snapshot.sample=i*500; xQueueOverwrite(stable.snapshots_,&snapshot);
            stable.step(); stable.step();
            assert(stable.stablePresence_==(i<AWS_PRESENCE_STABLE_SAMPLES?0:1));
        }
        assert(!stable.inflight_); // separacion minima
        Fake::now+=AWS_MIN_PUBLISH_INTERVAL_MS; stable.step(); assert(stable.inflight_);
        auto count=stable.mqtt_.topics.size();
        receive(stable,TOPIC_SHADOW_UPDATE_ACCEPTED,"{\"clientToken\":\"ajeno\"}");
        assert(stable.inflight_);
        Fake::now+=AWS_SHADOW_RESPONSE_TIMEOUT_MS;
        stable.step(); assert(stable.mqtt_.topics.size()==count+1);
        ack(stable);
        // Control nuevo tiene prioridad sobre informe pendiente de acuse.
        Fake::now+=AWS_MIN_PUBLISH_INTERVAL_MS; stable.current_.distance=40; stable.step();
        assert(stable.inflight_); auto oldToken=std::string(stable.token_);
        stable.current_.open=true; stable.step();
        assert(stable.inflight_ && std::string(stable.token_)!=oldToken);
        assert(stable.sent_.open);
        receive(stable,TOPIC_SHADOW_UPDATE_ACCEPTED,"{\"clientToken\":\""+oldToken+"\"}");
        assert(stable.inflight_); ack(stable);
        // Rechazo correlacionado suspende envios, sin martillar AWS.
        Fake::now+=AWS_MIN_PUBLISH_INTERVAL_MS; stable.current_.distance=50; stable.step();
        receive(stable,TOPIC_SHADOW_UPDATE_REJECTED,"{\"clientToken\":\""+std::string(stable.token_)+"\",\"code\":400}");
        assert(stable.rejectedBlocked_); count=stable.mqtt_.topics.size();
        Fake::now+=AWS_REPORT_INTERVAL_MS; stable.step(); assert(stable.mqtt_.topics.size()==count);
        stable.rejectedBlocked_=false;
        // Agotamiento de cuota no bloquea recibir comandos; no envia mas.
        stable.budget_.record.counts[ShadowBudget::Periodic]=AWS_MAX_SHADOW_UPDATES_PER_DAY;
        count=stable.mqtt_.topics.size();
        receive(stable,TOPIC_SHADOW_DELTA,"{\"version\":20,\"state\":{\"barrera\":\"cerrada\"}}");
        BarrierServo physicalDouble; assert(physicalDouble.begin());
        UltrasonicSensor sensorDouble; sensorDouble.begin();
        stable.tick(physicalDouble,sensorDouble);
        assert(physicalDouble.commandedState()==BarrierServo::State::Closed);
        Fake::now+=SERVO_TRAVEL_MS; physicalDouble.update(); stable.tick(physicalDouble,sensorDouble);
        stable.step(); assert(stable.mqtt_.topics.size()==count);
        // Limite de intentos conserva modo local.
        stable.disconnect(); stable.attempts_=AWS_MAX_CONNECTION_ATTEMPTS;
        count=stable.mqtt_.connects; stable.connectStep(Fake::now); assert(stable.mqtt_.connects==count);
        std::cout<<"PASS: AWS con dobles: GET unico, comandos, espera, reported, deduplicacion, versiones, distancia, presencia, periodo, cuota/reserva/NVS, backoff y demo\n";
    }
};
int main() { AwsIoTManagerTest::run(); }

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
        assert(b.advance(100)); b.record.counts[ShadowBudget::Periodic]=800;
        assert(!b.allows(ShadowBudget::Periodic,1000,200));
        assert(b.allows(ShadowBudget::Recovery,1000,200));
        assert(b.allows(ShadowBudget::Control,1000,200));
        assert(!b.advance(99) && b.total()==800);
        assert(!b.advance(100) && b.total()==800);
        b.record.counts[ShadowBudget::Control]=200;
        assert(!b.allows(ShadowBudget::Control,1000,200));
        assert(b.advance(101) && b.total()==0);

        static_assert(SENSOR_INTERVAL_MS==500 && AWS_REPORT_INTERVAL_MS==30000);
        static_assert(AWS_MIN_PUBLISH_INTERVAL_MS==10000 && AWS_DISTANCE_CHANGE_THRESHOLD_CM==10);
        static_assert(AWS_MAX_SHADOW_UPDATES_PER_DAY==1000 && AWS_RESERVED_CONTROL_UPDATES==200);
        static_assert(AWS_DEMO_MAX_CONNECTED_MS==3600000 && SERVO_TRAVEL_MS==700);
        // Agotar cada solicitud de ambos tramos, sin desbordar el techo.
        ShadowBudget exhaustive; exhaustive.advance(100);
        for (unsigned i=0;i<800;++i) {
            assert(exhaustive.allows(ShadowBudget::Sensor,1000,200));
            ++exhaustive.record.counts[ShadowBudget::Sensor];
        }
        assert(!exhaustive.allows(ShadowBudget::Periodic,1000,200));
        for (unsigned i=0;i<200;++i) {
            auto kind=i%2 ? ShadowBudget::Control : ShadowBudget::Recovery;
            assert(exhaustive.allows(kind,1000,200)); ++exhaustive.record.counts[kind];
        }
        for (auto kind : {ShadowBudget::Periodic,ShadowBudget::Sensor,ShadowBudget::Control,ShadowBudget::Recovery})
            assert(!exhaustive.allows(kind,1000,200));
        Fake::now=10000;
        AwsIoTManager a; init(a);
        a.connectStep(Fake::now);
        assert(a.mqtt_.connects==1 && a.mqtt_.subscriptions.size()==5);
        assert(a.mqtt_.topics.size()==1 && a.mqtt_.topics[0]==TOPIC_SHADOW_GET);
        a.step(); a.step(); assert(a.mqtt_.topics.size()==1); // GET unico
        auto getToken=std::string(a.token_);
        receive(a,TOPIC_SHADOW_GET_ACCEPTED,"{\"clientToken\":\""+getToken+"\",\"version\":1,\"state\":{\"reported\":{\"barrera\":\"cerrada\",\"distancia_cm\":20,\"vehiculo_detectado\":false}}}");
        assert(a.synced_ && a.haveConfirmed_ && a.attempts_==0);
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
        a.current_.distance=30; a.step(); assert(!a.inflight_);
        Fake::now+=AWS_MIN_PUBLISH_INTERVAL_MS-1; a.step(); assert(!a.inflight_);
        ++Fake::now;
        a.current_.distance=29.9f; a.step(); assert(!a.inflight_);
        a.current_.distance=30; a.step(); assert(a.inflight_); ack(a);
        assert(a.budget_.record.counts[ShadowBudget::Sensor]==1);
        Fake::now+=AWS_MIN_PUBLISH_INTERVAL_MS;
        a.stablePresence_=1; a.stableCount_=3; a.step(); assert(a.inflight_); ack(a);
        Fake::now+=AWS_REPORT_INTERVAL_MS-1; a.step(); assert(!a.inflight_);
        ++Fake::now; a.step(); assert(a.inflight_); ack(a);
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
        a.budget_.record.counts[ShadowBudget::Periodic]=800;
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
        a.clockMs_=Fake::now; a.connectedMs_=AWS_DEMO_MAX_CONNECTED_MS-1; a.step();
        assert(!a.demoEnded_); ++Fake::now; a.step();
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
        assert(stable.inflight_); // presencia prioritaria sin esperar 10 s
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
        assert(stable.mqtt_.bodies.back().find("\"barrera_posicion_estimada\":true")!=std::string::npos);
        receive(stable,TOPIC_SHADOW_UPDATE_ACCEPTED,"{\"clientToken\":\""+oldToken+"\"}");
        assert(stable.inflight_); ack(stable);
        // Presencia nueva desplaza distancia en vuelo, sin esperar acuse ni intervalo.
        Fake::now+=AWS_MIN_PUBLISH_INTERVAL_MS; stable.current_.distance=50; stable.step();
        oldToken=stable.token_; count=stable.mqtt_.topics.size();
        stable.stablePresence_=0; stable.step();
        assert(stable.mqtt_.topics.size()==count+1 && stable.sent_.presence==0);
        assert(std::string(stable.token_)!=oldToken); ack(stable);
        // Presencia no puede gastar la reserva; control si puede.
        auto priorBudget=stable.budget_.record;
        stable.budget_.record=ShadowBudgetRecord{}; stable.budget_.record.day=priorBudget.day;
        stable.budget_.record.counts[ShadowBudget::Periodic]=800;
        stable.stablePresence_=1; count=stable.mqtt_.topics.size(); stable.step();
        assert(stable.mqtt_.topics.size()==count && stable.budget_.total()==800);
        stable.controlPending_=true; stable.step();
        assert(stable.budget_.total()==801 && stable.inflightKind_==ShadowBudget::Control); ack(stable);
        stable.budget_.record=priorBudget;
        // Rechazo correlacionado suspende envios, sin martillar AWS.
        Fake::now+=AWS_MIN_PUBLISH_INTERVAL_MS; stable.current_.distance=60; stable.step();
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
        // Recuperacion puede usar reserva aun con 800 consumidas; WiFi tiene backoff.
        AwsIoTManager recovery; init(recovery);
        recovery.budget_.record.counts[ShadowBudget::Periodic]=800;
        WiFi.state=0; recovery.connectStep(Fake::now);
        assert(recovery.mqtt_.connects==0);
        WiFi.state=WL_CONNECTED; Fake::now=recovery.nextAttempt_;
        recovery.connectStep(Fake::now);
        assert(recovery.mqtt_.connects==1 && recovery.getPending_);
        assert(recovery.budget_.total()==801);
        assert(!recovery.reserve(ShadowBudget::Periodic));
        // Sin hora y NVS no hay solicitudes; nunca se borra el registro.
        auto saved=Preferences::disk;
        recovery.timeReady_=false; assert(!recovery.reserve(ShadowBudget::Recovery));
        assert(Preferences::disk==saved);
        // Un registro del firmware previo con 172 solicitudes se conserva al actualizar.
        ShadowBudgetRecord legacy; legacy.day=a.budget_.record.day; legacy.counts[0]=172;
        Preferences::disk.resize(sizeof(legacy)); std::memcpy(Preferences::disk.data(),&legacy,sizeof(legacy));
        AwsIoTManager upgraded; assert(upgraded.loadBudget()); upgraded.timeReady_=true;
        assert(upgraded.refreshDay() && upgraded.budget_.total()==172);
        assert(upgraded.budget_.allows(ShadowBudget::Recovery,1000,200));
        // Limite de intentos consecutivos conserva modo local.
        stable.disconnect(); stable.attempts_=AWS_MAX_CONNECTION_ATTEMPTS;
        count=stable.mqtt_.connects; stable.connectStep(Fake::now); assert(stable.mqtt_.connects==count);
        std::cout<<"PASS: AWS con dobles: GET unico, comandos, espera, reported, deduplicacion, versiones, distancia, presencia, periodo, cuota/reserva/NVS, backoff y demo\n";
    }
};
int main() { AwsIoTManagerTest::run(); }

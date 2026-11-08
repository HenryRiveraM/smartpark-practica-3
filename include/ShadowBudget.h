#pragma once
#include <stdint.h>

// Registro unico NVS: no reponer cuota al reiniciar ni al retroceder el reloj.
struct ShadowBudgetRecord {
    uint32_t magic = 0x53503201;
    uint32_t day = 0;
    uint32_t counts[4] = {};
};
class ShadowBudget {
public:
    enum Kind { Periodic, Sensor, Control, Recovery };
    ShadowBudgetRecord record;
    uint32_t total() const {
        return record.counts[0]+record.counts[1]+record.counts[2]+record.counts[3];
    }
    // Solo adelantar dias UTC; persistir el nuevo registro antes de habilitar envios.
    bool advance(uint32_t day) {
        if (day <= record.day) return false;
        record = ShadowBudgetRecord{}; record.day = day; return true;
    }
    bool allows(Kind kind, uint32_t limit, uint32_t reserved) const {
        return total() < ((kind == Control || kind == Recovery) ? limit : (reserved <= limit ? limit-reserved : 0));
    }
};

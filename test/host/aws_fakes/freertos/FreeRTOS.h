#pragma once
#include <cstddef>
using TaskHandle_t = void*;
constexpr int pdTRUE=1, pdPASS=1;
inline unsigned pdMS_TO_TICKS(unsigned n) { return n; }
inline void vTaskDelay(unsigned) {}
inline int xTaskCreate(void (*)(void*), const char*, unsigned, void*, unsigned, TaskHandle_t* t) { *t=reinterpret_cast<void*>(1); return pdPASS; }

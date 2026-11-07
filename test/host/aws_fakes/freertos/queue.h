#pragma once
#include <vector>
#include <cstring>
struct FakeQueue { std::vector<unsigned char> data; bool full=false; };
using QueueHandle_t = FakeQueue*;
inline QueueHandle_t xQueueCreate(unsigned, size_t size) { return new FakeQueue{std::vector<unsigned char>(size),false}; }
inline int xQueueOverwrite(QueueHandle_t q, const void* p) { std::memcpy(q->data.data(),p,q->data.size()); q->full=true; return 1; }
inline int xQueuePeek(QueueHandle_t q, void* p, unsigned) { if(!q->full) return 0; std::memcpy(p,q->data.data(),q->data.size()); return 1; }
inline int xQueueReceive(QueueHandle_t q, void* p, unsigned n) { int r=xQueuePeek(q,p,n); q->full=false; return r; }

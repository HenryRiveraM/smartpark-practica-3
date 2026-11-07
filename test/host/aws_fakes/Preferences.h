#pragma once
#include <vector>
#include <cstring>
class Preferences {
public:
    inline static std::vector<unsigned char> disk;
    inline static bool writable=true;
    bool begin(const char*,bool) { return true; }
    bool isKey(const char*) { return !disk.empty(); }
    size_t getBytesLength(const char*) { return disk.size(); }
    size_t getBytes(const char*,void* p,size_t n) { if(disk.size()!=n) return 0; std::memcpy(p,disk.data(),n); return n; }
    size_t putBytes(const char*,const void* p,size_t n) { if(!writable) return 0; disk.resize(n); std::memcpy(disk.data(),p,n); return n; }
};

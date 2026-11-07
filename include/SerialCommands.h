#pragma once
#include "config.h"
#include <ctype.h>
#include <string.h>
// Parser acotado, sin String ni asignacion dinamica. Una linea larga se descarta entera.
class SerialCommands {
public:
    enum class Command { None, Open, Close, Status, Distance, Help, Invalid };
    Command feed(char c) {
        if (c == '\r' || c == '\n') {
            if (overflow_) { reset(); return Command::Invalid; }
            buffer_[length_] = '\0';
            char* start = buffer_;
            while (*start == ' ' || *start == '\t') ++start;
            char* end = buffer_ + length_;
            while (end > start && (end[-1] == ' ' || end[-1] == '\t')) --end;
            *end = '\0';
            Command result = Command::Invalid;
            if (!*start) result = Command::None;
            else if (!strcmp(start, "OPEN")) result = Command::Open;
            else if (!strcmp(start, "CLOSE")) result = Command::Close;
            else if (!strcmp(start, "STATUS")) result = Command::Status;
            else if (!strcmp(start, "DISTANCE")) result = Command::Distance;
            else if (!strcmp(start, "HELP")) result = Command::Help;
            reset(); return result;
        }
        if (overflow_) return Command::None;
        if (length_ + 1 >= sizeof(buffer_) || (static_cast<unsigned char>(c) < 32 && c != '\t'))
            overflow_ = true;
        else buffer_[length_++] = static_cast<char>(toupper(static_cast<unsigned char>(c)));
        return Command::None;
    }
private:
    void reset() { length_ = 0; overflow_ = false; }
    char buffer_[COMMAND_CAPACITY]{};
    size_t length_ = 0;
    bool overflow_ = false;
};

// M300 Classic OEM print counter, GPL-3.0-or-later.
#ifndef __STM32_M300_FACTORY_COUNTER_H
#define __STM32_M300_FACTORY_COUNTER_H

#include <stdint.h>
#include "m300_factory.h"

#define M300_FACTORY_COUNTER_ABI 1
#define M300_FACTORY_COUNTER_SPAN (2 * M300_FACTORY_NVM_SIZE)
#define M300_FACTORY_COUNTER_NO_BANK 255u

enum m300_counter_result {
    M300_COUNTER_APPLIED,
    M300_COUNTER_ALREADY_APPLIED,
    M300_COUNTER_NOT_QUIESCENT,
    M300_COUNTER_INVALID_BANKS,
    M300_COUNTER_CONFLICT,
    M300_COUNTER_IO_ERROR,
    M300_COUNTER_INVALID_TARGET,
};

enum m300_counter_state {
    M300_COUNTER_UNAVAILABLE,
    M300_COUNTER_NORMALIZED,
    M300_COUNTER_RECOVERY_REQUIRED,
};

struct m300_counter_io {
    void *context;
    uint16_t (*read)(void *, unsigned offset);
    int (*program)(void *, unsigned offset, uint16_t value);
    int (*erase)(void *, unsigned offset);
    int (*write_allowed)(void *);
};

struct m300_counter_snapshot {
    uint32_t minutes, settings_crc;
    uint8_t state, source;
};

void m300_counter_inspect(const struct m300_counter_io *io,
                          struct m300_counter_snapshot *snapshot);
enum m300_counter_result
m300_counter_commit(const struct m300_counter_io *io, unsigned source,
                    uint32_t expected, uint32_t target, uint32_t settings_crc);

#endif

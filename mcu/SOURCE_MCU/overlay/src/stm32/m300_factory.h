// M300 stock factory ID3 decoder. Read-only; GPL-3.0-or-later.
#ifndef __STM32_M300_FACTORY_H
#define __STM32_M300_FACTORY_H
#include <stdint.h>

#define M300_FACTORY_ABI 1
#define M300_FACTORY_HW_ADDRESS 0x0803f848u
#define M300_FACTORY_HW_HEADER 0xaabb0103u

struct m300_factory_id {
    uint16_t z_steps;
    uint8_t valid, revision;
};

static inline struct m300_factory_id
m300_factory_decode(uint32_t header, uint8_t raw)
{
    struct m300_factory_id id = {0};
    // Stock stores revision+0xe0. Erased 0xff is never a hardware revision.
    if (header != M300_FACTORY_HW_HEADER || raw < 0xe0 || raw == 0xff)
        return id;
    id.valid = 1;
    id.revision = raw - 0xe0;
    id.z_steps = id.revision < 5 ? 800 : 400;
    return id;
}
#endif

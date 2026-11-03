// M300 stock factory ID3 decoder. Read-only; GPL-3.0-or-later.
#ifndef __STM32_M300_FACTORY_H
#define __STM32_M300_FACTORY_H
#include <stdint.h>

#define M300_FACTORY_ABI 1
#define M300_FACTORY_HW_ADDRESS 0x0803f848u
#define M300_FACTORY_HW_HEADER 0xaabb0103u
#define M300_FACTORY_INFO_ABI 1
#define M300_FACTORY_SERIAL_ADDRESS 0x0803f818u
#define M300_FACTORY_SERIAL_HEADER 0xaabb0401u
#define M300_FACTORY_NVM_A_ADDRESS 0x0803e800u
#define M300_FACTORY_NVM_B_ADDRESS 0x0803f000u
#define M300_FACTORY_NVM_SIZE 2048u

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

static inline uint32_t
m300_factory_serial(uint32_t header, const volatile uint8_t *data)
{
    if (header != M300_FACTORY_SERIAL_HEADER)
        return 0;
    uint32_t serial = ((uint32_t)data[0] << 24) | ((uint32_t)data[1] << 16)
        | ((uint32_t)data[2] << 8) | data[3];
    return serial == UINT32_MAX ? 0 : serial;
}

static inline uint16_t
m300_factory_le16(const volatile uint8_t *data)
{
    return data[0] | ((uint16_t)data[1] << 8);
}

static inline uint8_t
m300_factory_minutes(const volatile uint8_t *a, const volatile uint8_t *b,
                     uint32_t *minutes)
{
    uint16_t ha = m300_factory_le16(a), hb = m300_factory_le16(b);
    const volatile uint8_t *page;
    if (!ha && (hb == 0xffff || hb == 0xeeee))
        page = a;
    else if (!hb && (ha == 0xffff || ha == 0xeeee))
        page = b;
    else
        return 0;

    // Stock 1.3.1 writes ID0 (uint32 LE minutes) among other NVM records.
    static const uint8_t lengths[] = {4, 2, 2, 2, 2, 4, 4};
    uint32_t last = 0;
    uint8_t valid = 0;
    for (unsigned offset = 4; offset < M300_FACTORY_NVM_SIZE;) {
        uint16_t id = m300_factory_le16(page + offset);
        if (id == 0xffff) {
            for (; offset < M300_FACTORY_NVM_SIZE; offset++)
                if (page[offset] != 0xff)
                    return 0;
            break;
        }
        offset += 2;
        if (id >= sizeof(lengths) || lengths[id] > M300_FACTORY_NVM_SIZE - offset)
            return 0;
        if (!id) {
            const volatile uint8_t *value = page + offset;
            uint32_t candidate = m300_factory_le16(value)
                | ((uint32_t)m300_factory_le16(value + 2) << 16);
            if (candidate == UINT32_MAX)
                return 0;
            last = candidate;
            valid = 1;
        }
        offset += lengths[id];
    }
    if (valid)
        *minutes = last;
    return valid;
}
#endif

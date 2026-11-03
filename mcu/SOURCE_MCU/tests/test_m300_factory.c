// Exercise the decoder compiled into the actual MCU query. GPL-3.0-or-later.
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../overlay/src/stm32/m300_factory.h"

static void
test_information(void)
{
    const uint8_t serial[] = {0x12, 0x34, 0x56, 0x78};
    assert(m300_factory_serial(M300_FACTORY_SERIAL_HEADER, serial) == 0x12345678);
    assert(!m300_factory_serial(M300_FACTORY_HW_HEADER, serial));
    uint8_t a[M300_FACTORY_NVM_SIZE], b[M300_FACTORY_NVM_SIZE];
    memset(a, 0xff, sizeof(a));
    memset(b, 0xff, sizeof(b));
    const uint8_t records[] = {
        0, 0, 0xff, 0xff,           // active header
        0, 0, 1, 0, 0, 0,           // earlier ID0, one minute
        3, 0, 1, 0,                 // two-byte language record
        0, 0, 0x0c, 0x60, 0x04, 0   // last ID0, 286732 minutes
    };
    memcpy(a, records, sizeof(records));
    uint32_t minutes;
    assert(m300_factory_minutes(a, b, &minutes) && minutes == 286732);
    assert(m300_factory_minutes(b, a, &minutes) && minutes == 286732);
    b[0] = b[1] = 0xee;
    assert(m300_factory_minutes(a, b, &minutes) && minutes == 286732);
    b[0] = b[1] = 0;
    assert(!m300_factory_minutes(a, b, &minutes));
    b[0] = b[1] = 0xff;
    memset(a + sizeof(records) - 4, 0, 4);
    assert(m300_factory_minutes(a, b, &minutes) && minutes == 0);
    a[sizeof(records)] = 7;
    assert(!m300_factory_minutes(a, b, &minutes));
}

int main(void)
{
    unsigned cases = 0;
    const uint32_t headers[] = {
        M300_FACTORY_HW_HEADER, 0xffffffff, 0xaabb0003, 0xaabb0203,
        0xaabb0102, 0, 0x0301bbaa
    };
    for (unsigned h = 0; h < sizeof(headers) / sizeof(headers[0]); h++) {
        for (unsigned raw = 0; raw < 256; raw++) {
            struct m300_factory_id id = m300_factory_decode(headers[h], raw);
            int valid = h == 0 && raw >= 0xe0 && raw < 0xff;
            assert(id.valid == valid);
            if (valid) {
                assert(id.revision == raw - 0xe0);
                assert(id.z_steps == (raw < 0xe5 ? 800 : 400));
            } else {
                assert(id.z_steps == 0 && id.revision == 0);
            }
            cases++;
        }
    }
    test_information();
    printf("PASS_FACTORY_ID3 cases=%u\n", cases);
    return 0;
}

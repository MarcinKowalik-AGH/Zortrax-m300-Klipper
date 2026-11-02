// Exercise the decoder compiled into the actual MCU query. GPL-3.0-or-later.
#include <assert.h>
#include <stdio.h>
#include "../overlay/src/stm32/m300_factory.h"

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
    printf("PASS_FACTORY_ID3 cases=%u\n", cases);
    return 0;
}

// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef M300_OLED_RLE_H
#define M300_OLED_RLE_H

#include <stdint.h>
#include <string.h>

static inline void
oled_fill_run(uint8_t *dest, uint8_t value, unsigned count)
{
#if defined(__ARM_ARCH_7M__)
    if (count >= 12) {
        // The DMA slot starts at a byte offset. Align before using word stores.
        while ((uintptr_t)dest & 3) {
            *dest++ = value;
            count--;
        }
        uint32_t word = value * 0x01010101u;
        unsigned words = count / 4;
        __asm__ volatile(
            "1: str %[word], [%[dest]], #4\n\t"
            "subs %[words], %[words], #1\n\t"
            "bne 1b"
            : [dest] "+&r" (dest), [words] "+&r" (words)
            : [word] "r" (word)
            : "cc", "memory");
        count %= 4;
    }
#endif
    if (count)
        memset(dest, value, count);
}

#endif // M300_OLED_RLE_H

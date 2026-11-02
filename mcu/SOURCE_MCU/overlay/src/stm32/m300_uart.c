// SPDX-License-Identifier: GPL-3.0-or-later
// Read-only adapter for the M300Boot v1.1 F103 HALFWORD journal.
#include "m300_uart.h"
#ifndef M300_UART_TEST
#include "command.h"
#include "sched.h"
#endif

static const uint8_t codes[] = {0x0f, 0x33, 0x55, 0xaa, 0xcc, 0xf0, 0x66, 0x99};
static const uint32_t rates[] = {19200, 57600, 115200, 250000, 500000, 750000, 1000000, 1500000};
static struct m300_uart_selection selection;

void
m300_uart_decode(const volatile uint16_t *journal,
                 struct m300_uart_selection *out)
{
    *out = (struct m300_uart_selection){.baud=M300_UART_DEFAULT, .index=3};
    for (unsigned i=0; i<M300_UART_SLOTS; i++) {
        uint16_t half = journal[i];
        // Exactly p4_flash.c: an invalid high byte invalidates the whole slot.
        uint8_t code = (half & 0xff00u) == 0xff00u ? half : 0;
        if (code == 0xffu)
            continue;
        out->used = i+1u;
        unsigned matched = 0;
        for (unsigned n=0; n<8; n++)
            if (code == codes[n]) {
                out->index=n; out->saved=1; matched=1;
                break;
            }
        if (!matched) out->invalid++;
    }
    out->baud = rates[out->index];
}

uint32_t
m300_uart_baud(void)
{
    if (!selection.baud)
        m300_uart_decode((const volatile uint16_t *)M300_UART_STORE_BASE,
                         &selection);
    return selection.baud;
}

#ifndef M300_UART_TEST
DECL_CONSTANT("M300_UART_PERSIST_ABI", 1);
DECL_CONSTANT("M300_UART_DEFAULT_BAUD", M300_UART_DEFAULT);
DECL_CONSTANT("M300_UART_RATE_COUNT", 8);
void command_m300_uart_query(uint32_t *args)
{
    (void)args;
    uint32_t baud=m300_uart_baud();
    sendf("m300_uart_state baud=%u saved=%c index=%c used=%hu invalid=%hu",
          baud,selection.saved,selection.index,selection.used,selection.invalid);
}
DECL_COMMAND_FLAGS(command_m300_uart_query,HF_IN_SHUTDOWN,"m300_uart_query");
#endif

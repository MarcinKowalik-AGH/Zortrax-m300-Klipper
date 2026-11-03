// SPDX-License-Identifier: GPL-3.0-or-later
// M300Boot baud journal and passive USART1 receive diagnostics.
#include "m300_uart.h"
#ifndef M300_UART_TEST
#include "board/irq.h"
#include "board/misc.h"
#include "command.h"
#include "sched.h"
#endif

static const uint8_t codes[] = {0x0f, 0x33, 0x55, 0xaa, 0xcc, 0xf0, 0x66, 0x99};
static const uint32_t rates[] = {19200, 57600, 115200, 250000, 500000, 750000, 1000000, 1500000};
static struct m300_uart_selection selection;
static volatile struct m300_uart_rx_stats rx_stats;

void
m300_uart_rx_note_error(bool overrun, bool framing, bool noise)
{
    rx_stats.overrun += overrun;
    rx_stats.framing += framing;
    rx_stats.noise += noise;
}

void
m300_uart_rx_note_buffer_drop(void)
{
    rx_stats.buffer_drops++;
}

struct m300_uart_rx_stats
m300_uart_rx_snapshot(void)
{
#ifndef M300_UART_TEST
    irqstatus_t flag = irq_save();
#endif
    struct m300_uart_rx_stats result = rx_stats;
#ifndef M300_UART_TEST
    irq_restore(flag);
#endif
    return result;
}

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
DECL_CONSTANT("M300_UART_RX_DIAG_ABI", 1);
void command_m300_uart_query(uint32_t *args)
{
    (void)args;
    uint32_t baud=m300_uart_baud();
    sendf("m300_uart_state baud=%u saved=%c index=%c used=%hu invalid=%hu",
          baud,selection.saved,selection.index,selection.used,selection.invalid);
}
DECL_COMMAND_FLAGS(command_m300_uart_query,HF_IN_SHUTDOWN,"m300_uart_query");

void
command_m300_uart_rx_query(uint32_t *args)
{
    (void)args;
    struct m300_uart_rx_stats stats = m300_uart_rx_snapshot();
    sendf("m300_uart_rx_state clock=%u overrun=%u framing=%u"
          " noise=%u buffer_drops=%u", timer_read_time(), stats.overrun,
          stats.framing, stats.noise, stats.buffer_drops);
}
DECL_COMMAND_FLAGS(command_m300_uart_rx_query, HF_IN_SHUTDOWN, "m300_uart_rx_query");
#endif

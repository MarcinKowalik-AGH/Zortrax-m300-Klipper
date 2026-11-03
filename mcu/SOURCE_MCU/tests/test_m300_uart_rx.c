// SPDX-License-Identifier: GPL-3.0-or-later
#include <assert.h>
#define M300_UART_TEST
#include "../overlay/src/stm32/m300_uart.c"

int
main(void)
{
    struct m300_uart_rx_stats initial = m300_uart_rx_snapshot();
    assert(!initial.overrun && !initial.framing && !initial.noise
           && !initial.buffer_drops);
    m300_uart_rx_note_error(true, false, false);
    m300_uart_rx_note_error(false, true, true);
    m300_uart_rx_note_error(false, false, true);
    m300_uart_rx_note_buffer_drop();
    struct m300_uart_rx_stats first = m300_uart_rx_snapshot();
    struct m300_uart_rx_stats second = m300_uart_rx_snapshot();
    assert(first.overrun == 1 && first.framing == 1 && first.noise == 2
           && first.buffer_drops == 1);
    assert(second.overrun == first.overrun && second.framing == first.framing
           && second.noise == first.noise && second.buffer_drops == first.buffer_drops);
    rx_stats.overrun = UINT32_MAX;
    m300_uart_rx_note_error(true, false, false);
    assert(m300_uart_rx_snapshot().overrun == 0);
}

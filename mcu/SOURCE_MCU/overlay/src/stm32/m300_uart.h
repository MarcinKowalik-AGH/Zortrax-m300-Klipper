// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef M300_UART_H
#define M300_UART_H
#include <stdbool.h>
#include <stdint.h>
#define M300_UART_STORE_BASE 0x0803d800u
#define M300_UART_SLOTS 256u
#define M300_UART_DEFAULT 250000u
struct m300_uart_selection {
    uint32_t baud;
    uint16_t used, invalid;
    uint8_t saved, index;
};
struct m300_uart_rx_stats {
    uint32_t overrun, framing, noise, buffer_drops;
};
void m300_uart_decode(const volatile uint16_t *journal,
                      struct m300_uart_selection *out);
uint32_t m300_uart_baud(void);
void m300_uart_rx_note_error(bool overrun, bool framing, bool noise);
void m300_uart_rx_note_buffer_drop(void);
struct m300_uart_rx_stats m300_uart_rx_snapshot(void);
#endif

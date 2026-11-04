#ifndef __STM32_M300_XY_STEP_DMA_H
#define __STM32_M300_XY_STEP_DMA_H
// Classic M300 experimental constant-period STEP blocks. GPL-3.0-or-later.
#include <stdint.h>

#define M300_XY_DMA_EDGE_MARGIN 32u

uint8_t m300_xy_dma_axis(uint32_t pin);
uint8_t m300_xy_dma_eligible(uint32_t period, uint32_t pulse, uint32_t count);
uint32_t m300_xy_dma_start(uint8_t axis, uint32_t period, uint32_t pulse,
                          uint32_t count, uint32_t first_clock);
uint8_t m300_xy_dma_chain(uint8_t axis, uint32_t period, uint32_t count,
                         uint32_t last_rise_clock);
uint32_t m300_xy_dma_remaining(uint8_t axis);
uint32_t m300_xy_dma_stop(uint8_t axis);
void m300_xy_dma_finish(uint8_t axis, uint32_t deadline, uint32_t nominal_last);
void m300_xy_dma_abort_all(void);

#endif

#ifndef __STM32_M300_XY_STEP_TIMER_H
#define __STM32_M300_XY_STEP_TIMER_H
// Finite Classic M300 STEP pulse trains. GPL-3.0-or-later.
#include <stdint.h>

#define M300_XY_TIMER_HIGH_MARGIN 32u
#define M300_XY_TIMER_GATE_MARGIN 32u

void m300_xy_timer_remap(void);
uint8_t m300_xy_timer_axis(uint32_t pin);
uint8_t m300_xy_timer_eligible(uint32_t period, uint32_t pulse, uint32_t count);
uint32_t m300_xy_timer_start(uint8_t axis, uint32_t period, uint32_t pulse,
                             uint32_t count, uint32_t first_clock);
uint32_t m300_xy_timer_chain(uint8_t axis, uint32_t period, uint32_t count,
                             uint32_t first_clock);
uint32_t m300_xy_timer_remaining(uint8_t axis);
uint32_t m300_xy_timer_stop(uint8_t axis);
void m300_xy_timer_finish(uint8_t axis);
void m300_xy_timer_abort_all(void);

#endif

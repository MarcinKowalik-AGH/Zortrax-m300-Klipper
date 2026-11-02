// Isolated MCU timer scheduler test. Does not emulate STM32 timing.
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
static uint32_t timer_from_us(uint32_t us) {return us * 72u;}
#include "../overlay/src/stm32/m300_sched.h"
int main(void) {
    uint32_t period = timer_from_us(1000);
    uint32_t start = 720000;
    // Preserve cadence when 100 us into the interval.
    assert(m300_next_timer(start, start + timer_from_us(100), period)
           == start+period);
    // Skip overdue callback instead of scheduling in the past.
    assert(m300_next_timer(start, start + 4*period, period)
           == start+5*period);
    // Honor a 200 us minimum horizon even if deadline barely ahead.
    assert(m300_next_timer(start, start + period - timer_from_us(100), period)
           == start + 2*period - timer_from_us(100));
    // 32-bit wrap-around must be interpreted as relative time.
    start=UINT32_MAX - timer_from_us(300);
    uint32_t normal = (uint32_t)(start + period);
    assert(m300_next_timer(start, start + timer_from_us(100), period)==normal);
    // Idle SD period never less than 5 ms, busy SD remains 1 ms.
    assert(timer_from_us(5000)>timer_from_us(1000));
    puts("PASS_M300_TIMER_DEADLINE_5_CASES");
    return 0;
}

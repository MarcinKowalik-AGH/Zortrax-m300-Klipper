// SPDX-License-Identifier: GPL-3.0-or-later
// M300 timer rescheduling: do not insert a catch-up timer in the past.
// Called from timer callbacks after their work. A missed interval is not
// recovered by generating a burst of overdue callbacks; tasks sample now.
#ifndef M300_SCHED_H
#define M300_SCHED_H
#include <stdint.h>
static inline uint32_t
m300_next_timer(uint32_t old_deadline, uint32_t now, uint32_t period)
{
    // 200 us minimum insertion horizon, independent of timer wrap.
    uint32_t next = old_deadline + period;
    if ((int32_t)(next - (now + timer_from_us(200))) < 0)
        next = now + period;
    return next;
}
#endif

// SPDX-License-Identifier: GPL-3.0-or-later
// Exercise the transformed production timer-list code, without physical I/O.
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define CONFIG_M300_CLASSIC 1
#define CONFIG_INLINE_STEPPER_HACK 0
#define CONFIG_MACH_AVR 0
#undef __always_inline
#define __always_inline
#define __noreturn __attribute__((noreturn))
#define likely(x) (x)
#define unlikely(x) (x)
#define readb(p) (*(p))
#define writeb(p, v) (*(p) = (v))
#define shutdown(...) abort()
#define try_shutdown(...) abort()
#define sendf(...) do { if (0) printf(__VA_ARGS__); } while (0)

#include "sched.h"

static uint32_t now;
static int irq_masked;
static unsigned kicks;

typedef int irqstatus_t;

static uint32_t timer_read_time(void) { return now; }
static uint32_t timer_from_us(uint32_t us) { return us * 72u; }
static uint8_t timer_is_before(uint32_t a, uint32_t b)
{
    return (int32_t)(a - b) < 0;
}

static irqstatus_t irq_save(void)
{
    int old = irq_masked;
    irq_masked = 1;
    return old;
}

static void irq_restore(irqstatus_t flag) { irq_masked = flag; }
static void irq_disable(void) { irq_masked = 1; }
static void irq_enable(void) { irq_masked = 0; }
static void irq_poll(void) {}
static void irq_wait(void) { abort(); }
static void timer_kick(void) { kicks++; }
static void stats_update(uint32_t start, uint32_t stop) {}
static void m300_error_shutdown(unsigned reason) {}
static uint_fast8_t stepper_event(struct timer *timer) { abort(); }
void ctr_run_initfuncs(void) {}
void ctr_run_taskfuncs(void) {}
void ctr_run_shutdownfuncs(void) {}

static struct timer panel, oled, led, guard, sd, future_led, adc, motion;
static unsigned tolerant_dispatches, strict_dispatches;
static int led_settled, panel_idle, sd_idle;

static uint_fast8_t tolerant_event(struct timer *timer)
{
    tolerant_dispatches++;
    timer->waketime = now + timer_from_us(1000);
    return SF_RESCHEDULE;
}

static uint_fast8_t strict_event(struct timer *timer)
{
    strict_dispatches++;
    return SF_DONE;
}

// Production classifier consults board owners. The fixture models their
// register state so both idle and active timers use the real scheduler.
int m300_factory_board_timer(const struct timer *timer) { return timer == &guard; }
int m300_factory_panel_timer(const struct timer *timer)
{
    return timer == &oled || (panel_idle && timer == &panel);
}
int m300_factory_sd_timer(const struct timer *timer) { return sd_idle && timer == &sd; }
int m300_factory_led_timer(const struct timer *timer)
{
    return led_settled && (timer == &led || timer == &future_led);
}

#include "native_sched.c"

static void reset(uint32_t epoch)
{
    now = epoch;
    kicks = tolerant_dispatches = strict_dispatches = 0;
    irq_masked = 1;
    led_settled = panel_idle = sd_idle = 1;
    SchedStatus = (typeof(SchedStatus)){
        .timer_list = &periodic_timer,
        .last_insert = &periodic_timer,
    };
    periodic_timer.waketime = now + timer_from_us(100000);
    periodic_timer.next = &sentinel_timer;
    sentinel_timer.waketime = periodic_timer.waketime + 0x80000000;
    sentinel_timer.next = NULL;
    deleted_timer.func = deleted_event;
    deleted_timer.next = NULL;
    panel = oled = led = guard = sd = future_led = (struct timer){.func = tolerant_event};
    adc = motion = (struct timer){.func = strict_event};
}

static void schedule(struct timer *timer, uint32_t offset)
{
    timer->waketime = now + timer_from_us(offset);
    sched_add_timer(timer);
}

static void assert_ordered(void)
{
    unsigned count = 0;
    for (struct timer *timer = SchedStatus.timer_list; timer->next;
         timer = timer->next) {
        assert(++count < 12);
        // The upstream sentinel is intentionally exactly half a clock wrap
        // past the periodic timer, outside the normal ordering horizon.
        if (timer->next != &sentinel_timer)
            assert(!timer_is_before(timer->next->waketime, timer->waketime));
    }
}

static void test_mixed_deadlines(uint32_t epoch)
{
    reset(epoch);
    schedule(&panel, 1000);
    schedule(&oled, 1500);
    schedule(&led, 2000);
    schedule(&sd, 5000);
    schedule(&guard, 10000);
    schedule(&adc, 80000);
    schedule(&motion, 90000);
    schedule(&future_led, 85000);
    assert(m300_factory_timer_margin() == (int32_t)timer_from_us(80000));
    uint32_t adc_due = adc.waketime, motion_due = motion.waketime;
    uint32_t periodic_due = periodic_timer.waketime;
    uint32_t led_due = future_led.waketime;
    now += timer_from_us(40000);
    m300_factory_rebase_timers();
    m300_factory_rebase_timers(); // Already-installed no-op is not duplicated.
    assert(irq_masked);
    assert(adc.waketime == adc_due && motion.waketime == motion_due);
    assert(periodic_timer.waketime == periodic_due);
    assert(future_led.waketime == led_due);
    assert(!tolerant_dispatches && !strict_dispatches);
    assert_ordered();
    for (unsigned i = 0; i < 7 && tolerant_dispatches < 5; i++) {
        assert(SchedStatus.timer_list != &adc);
        uint32_t due = SchedStatus.timer_list->waketime;
        if (timer_is_before(now, due))
            now = due;
        uint32_t next = sched_timer_dispatch();
        // Klipper's Cortex-M dispatcher shuts down when the next timer is
        // already more than 1ms old. A second overdue callback must be gone.
        assert((int32_t)(next - now) >= -(int32_t)timer_from_us(1000));
        if (tolerant_dispatches >= 5)
            break;
    }
    assert(tolerant_dispatches == 5 && !strict_dispatches);
    assert_ordered();
}

static void test_active_native_work(void)
{
    reset(0);
    schedule(&motion, 800);
    schedule(&panel, 1000);
    assert(m300_factory_timer_margin() == (int32_t)timer_from_us(800));
    sched_del_timer(&motion);
    schedule(&led, 2000);
    schedule(&sd, 3000);
    schedule(&adc, 12000);
    assert(m300_factory_timer_margin() == (int32_t)timer_from_us(12000));
    led_settled = 0;
    assert(m300_factory_timer_margin() == (int32_t)timer_from_us(2000));
    panel_idle = 0;
    assert(m300_factory_timer_margin() == (int32_t)timer_from_us(1000));
    panel_idle = 1;
    led_settled = 1;
    sd_idle = 0;
    assert(m300_factory_timer_margin() == (int32_t)timer_from_us(3000));
}

static void test_default_adc_window(void)
{
    // FILEOUTPUT initial ADC clocks are 90 ms apart. Eight 1 ms samples
    // per stream leave a >=65 ms gap at a periodic edge in each 300 ms
    // cycle, even when the native ADC epoch starts at an arbitrary phase.
    for (unsigned phase = 0; phase < 300000; phase += 100) {
        unsigned possible = 0;
        for (unsigned edge = 0; edge < 300000; edge += 100000) {
            reset(0);
            unsigned first = (phase + 300000 - edge) % 300000;
            unsigned second = (first + 90000) % 300000;
            if (first > 292000 || second > 292000)
                continue; // Periodic edge fell inside an ADC burst.
            schedule(&panel, 1000);
            schedule(&led, 2000);
            schedule(&adc, first);
            schedule(&motion, second); // second native ADC timer
            if (m300_factory_timer_margin() >= (int32_t)timer_from_us(65000))
                possible++;
        }
        assert(possible);
    }
}

int main(void)
{
    test_mixed_deadlines(0);
    test_mixed_deadlines(UINT32_MAX - timer_from_us(15000));
    test_active_native_work();
    test_default_adc_window();
    puts("PASS M300 factory runtime scheduler, mixed/wrapped timers and 3000 ADC phases");
    return 0;
}

// Finite Classic M300 STEP pulse trains. GPL-3.0-or-later.
#include "board/gpio.h" // GPIO
#include "board/irq.h" // irq_save
#include "board/misc.h" // timer_read_time
#include "command.h" // shutdown
#include "internal.h" // enable_pclock
#include "m300.h" // m300_require_motion
#include "m300_xy_step_timer.h"
#include "sched.h" // DECL_INIT

struct xy_timer_axis {
    TIM_TypeDef *pulse, *gate;
    uint32_t output_enable, pulse_trigger, gate_trigger;
    uint8_t pin;
};

// RM0008 table 86. TIM2_CH2/PB3 uses TIM4; TIM3_CH1/PB4 uses TIM5.
// PWM1 generates the physical pulse. CH1 compare, at the falling edge,
// clocks the gate counter. The gate drops when its CNT reaches CCR1.
static const struct xy_timer_axis axes[] = {
    {TIM2, TIM4, TIM_CCER_CC2E, 3u << 4, 1u << 4, 3},
    {TIM3, TIM5, TIM_CCER_CC1E, 2u << 4, 1u << 4, 4},
};
static uint8_t active, initialized, first_reported, pending_report;
static struct task_wake report_wake;

static uint32_t
pin_mask(const struct xy_timer_axis *a)
{
    return 1u << a->pin;
}

static void
pin_mode(const struct xy_timer_axis *a, uint32_t mode)
{
    unsigned shift = 4u * a->pin;
    GPIOB->CRL = (GPIOB->CRL & ~(15u << shift)) | (mode << shift);
}

uint8_t
m300_xy_timer_axis(uint32_t pin)
{
    if (pin == GPIO('B', 3))
        return 1;
    if (pin == GPIO('B', 4))
        return 2;
    return 0;
}

uint8_t
m300_xy_timer_eligible(uint32_t period, uint32_t pulse, uint32_t count)
{
    return pulse == 144 && count >= 32 && period <= 720
        && period >= 2 * (pulse + M300_XY_TIMER_HIGH_MARGIN);
}

void
m300_xy_timer_init(void)
{
    m300_xy_timer_remap();
    for (unsigned i = 0; i < sizeof(axes) / sizeof(axes[0]); i++) {
        const struct xy_timer_axis *a = &axes[i];
        TIM_TypeDef *p = a->pulse, *g = a->gate;
        enable_pclock((uint32_t)(uintptr_t)p);
        enable_pclock((uint32_t)(uintptr_t)g);
        p->CR1 = p->DIER = p->CCER = p->CCMR1 = p->PSC = 0;
        p->CR2 = 3u << 4; // Compare pulse TRGO on CC1 match.
        p->SMCR = a->pulse_trigger | 5u; // Gated mode.
        g->CR1 = g->DIER = g->CCER = g->PSC = 0;
        g->CR2 = 4u << 4; // OC1REF as TRGO.
        g->SMCR = a->gate_trigger | 7u; // External clock mode 1.
        g->CCMR1 = 6u << 4; // PWM1: gate high while CNT < CCR1.
        g->ARR = 65535;
        g->CCR1 = 0;
        g->EGR = TIM_EGR_UG;
    }
    initialized = 1;
}
DECL_INIT(m300_xy_timer_init);

static uint32_t
launch(const struct xy_timer_axis *a, uint32_t period, uint32_t count,
       uint32_t first_clock)
{
    TIM_TypeDef *p = a->pulse, *g = a->gate;
    // The pulse timer is stopped. Set CNT in the inactive part of PWM before
    // reopening its gate. A software register write never supplies a STEP.
    p->ARR = period - 1;
    g->CR1 = 0;
    g->CCR1 = count;
    g->EGR = TIM_EGR_UG;
    g->CNT = 0;
    g->CR1 = TIM_CR1_CEN;
    uint32_t now = timer_read_time();
    int32_t delay = first_clock - now;
    if (delay < -(int32_t)timer_from_us(1000))
        shutdown("M300 XY STEP timer start late");
    uint32_t lead = delay > 1 ? (uint32_t)delay : 1;
    if (lead >= period - p->CCR1)
        shutdown("M300 XY STEP timer invalid start phase");
    p->CNT = period - lead;
    p->CR1 = TIM_CR1_CEN;
    (void)p->CR1;
    return timer_read_time() + lead;
}

uint32_t
m300_xy_timer_start(uint8_t axis, uint32_t period, uint32_t pulse,
                    uint32_t count, uint32_t first_clock)
{
    const struct xy_timer_axis *a = &axes[axis - 1];
    TIM_TypeDef *p = a->pulse;
    m300_require_motion();
    if ((active & (1u << (axis - 1))) || (GPIOB->IDR & pin_mask(a)))
        shutdown("M300 XY STEP timer start with active output");
    p->CCMR1 = 0; // Freeze while initializing the counter and compare.
    p->CCR1 = pulse + M300_XY_TIMER_HIGH_MARGIN;
    p->CCR2 = p->CCR1;
    p->ARR = period - 1;
    p->EGR = TIM_EGR_UG;
    p->CNT = period - 1;
    p->CCMR1 = a->output_enable == TIM_CCER_CC2E ? 6u << 12 : 6u << 4;
    p->CCER = a->output_enable;
    pin_mode(a, 0x9); // Alternate-function push-pull, 10 MHz.
    active |= 1u << (axis - 1);
    return launch(a, period, count, first_clock);
}

static void
report_completed_block(uint8_t axis)
{
    uint8_t mask = 1u << (axis - 1);
    if (!(first_reported & mask)) {
        first_reported |= mask;
        pending_report |= mask;
        sched_wake_task(&report_wake);
    }
}

static void
check_complete(const struct xy_timer_axis *a)
{
    if (a->gate->CNT != a->gate->CCR1 || (GPIOB->IDR & pin_mask(a)))
        shutdown("M300 XY STEP timer incomplete pulse train");
}

uint32_t
m300_xy_timer_chain(uint8_t axis, uint32_t period, uint32_t count,
                    uint32_t first_clock)
{
    const struct xy_timer_axis *a = &axes[axis - 1];
    check_complete(a);
    m300_require_motion_gate();
    a->pulse->CR1 = 0;
    uint32_t first = launch(a, period, count, first_clock);
    report_completed_block(axis);
    return first;
}

static uint32_t
remaining(const struct xy_timer_axis *a, uint32_t count, uint32_t high)
{
    uint32_t target = a->gate->CCR1;
    // The gate counts falling edges. An active high pulse already emitted
    // its rising edge and must also count in the reported position.
    return count + high < target ? target - count - high : 0;
}

uint32_t
m300_xy_timer_remaining(uint8_t axis)
{
    const struct xy_timer_axis *a = &axes[axis - 1];
    uint32_t count, high;
    do {
        count = a->gate->CNT;
        high = !!(GPIOB->IDR & pin_mask(a));
    } while (a->gate->CNT != count);
    return remaining(a, count, high);
}

static void
detach(const struct xy_timer_axis *a)
{
    GPIOB->BSRR = pin_mask(a) << 16;
    pin_mode(a, 0x1); // GPIO push-pull, low.
    a->pulse->CCER = 0;
    a->gate->CR1 = 0;
}

uint32_t
m300_xy_timer_stop(uint8_t axis)
{
    const struct xy_timer_axis *a = &axes[axis - 1];
    if (!(active & (1u << (axis - 1))))
        return remaining(a, a->gate->CNT, 0);
    a->pulse->CR1 = 0;
    (void)a->pulse->CR1;
    uint32_t high = !!(GPIOB->IDR & pin_mask(a));
    // Allow the internal trigger to reach the gate counter after a fall.
    // If still high, complete the minimum pulse width before forcing low.
    uint32_t until = timer_read_time() + (high ? timer_from_us(2) : 16u);
    while (timer_is_before(timer_read_time(), until))
        ;
    uint32_t left = remaining(a, a->gate->CNT, high);
    detach(a);
    active &= ~(1u << (axis - 1));
    return left;
}

void
m300_xy_timer_finish(uint8_t axis)
{
    const struct xy_timer_axis *a = &axes[axis - 1];
    check_complete(a);
    a->pulse->CR1 = 0;
    detach(a);
    active &= ~(1u << (axis - 1));
    report_completed_block(axis);
}

void
m300_xy_timer_report_task(void)
{
    if (!sched_check_wake(&report_wake))
        return;
    irqstatus_t flag = irq_save();
    uint8_t report_mask = pending_report;
    pending_report = 0;
    irq_restore(flag);
    if (report_mask & 1)
        output("M300 XY STEP timer completed first X block");
    if (report_mask & 2)
        output("M300 XY STEP timer completed first Y block");
}
DECL_TASK(m300_xy_timer_report_task);

void
m300_xy_timer_abort_all(void)
{
    if (!initialized)
        return;
    for (unsigned i = 0; i < sizeof(axes) / sizeof(axes[0]); i++) {
        const struct xy_timer_axis *a = &axes[i];
        a->pulse->CR1 = 0;
        if (active & (1u << i))
            detach(a);
    }
    active = 0;
}

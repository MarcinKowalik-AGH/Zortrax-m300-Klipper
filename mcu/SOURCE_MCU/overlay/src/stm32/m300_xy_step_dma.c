// Classic M300 experimental finite STEP transfers. GPL-3.0-or-later.
#include "board/gpio.h" // GPIO
#include "board/irq.h" // irq_save
#include "board/misc.h" // timer_read_time
#include "command.h" // shutdown
#include "generic/armcm_boot.h" // armcm_enable_irq
#include "internal.h" // enable_pclock
#include "m300.h" // m300_require_motion
#include "m300_xy_step_dma.h"
#include "sched.h" // DECL_INIT

struct xy_dma_axis {
    TIM_TypeDef *timer;
    volatile uint32_t *compare;
    DMA_Channel_TypeDef *rise, *fall;
    uint32_t compare_request, flags;
    uint32_t high, low;
};

// RM0008 DMA1 map. Update sets STEP, compare clears it. Both are finite
// single-word-source transfers. GPIO stays push-pull and SPI2 keeps CH5.
static const struct xy_dma_axis axes[] = {
    {TIM2, &TIM2->CCR2, DMA1_Channel2, DMA1_Channel7, TIM_DIER_CC2DE,
     DMA_ISR_GIF2 | DMA_ISR_TCIF2 | DMA_ISR_HTIF2 | DMA_ISR_TEIF2
     | DMA_ISR_GIF7 | DMA_ISR_TCIF7 | DMA_ISR_HTIF7 | DMA_ISR_TEIF7,
     1u << 3, 1u << 19},
    {TIM3, &TIM3->CCR1, DMA1_Channel3, DMA1_Channel6, TIM_DIER_CC1DE,
     DMA_ISR_GIF3 | DMA_ISR_TCIF3 | DMA_ISR_HTIF3 | DMA_ISR_TEIF3
     | DMA_ISR_GIF6 | DMA_ISR_TCIF6 | DMA_ISR_HTIF6 | DMA_ISR_TEIF6,
     1u << 4, 1u << 20},
};

static const uint32_t channel_mode = DMA_CCR_DIR | DMA_CCR_PSIZE_1
    | DMA_CCR_MSIZE_1 | DMA_CCR_PL_1 | DMA_CCR_PL_0 | DMA_CCR_TEIE;
static const uint32_t transfer_errors =
    DMA_ISR_TEIF2 | DMA_ISR_TEIF3 | DMA_ISR_TEIF6 | DMA_ISR_TEIF7;
static uint8_t initialized, first_reported, pending_report;
static uint8_t last_chained[sizeof(axes) / sizeof(axes[0])];
static struct task_wake report_wake;
static struct {
    uint32_t clock, deadline, nominal_last, flags;
    uint16_t rise, fall, counter, period, compare;
    uint8_t axis, chained;
} fault_snapshot;

uint8_t
m300_xy_dma_axis(uint32_t pin)
{
    if (pin == GPIO('B', 3))
        return 1;
    if (pin == GPIO('B', 4))
        return 2;
    return 0;
}

uint8_t
m300_xy_dma_eligible(uint32_t period, uint32_t pulse, uint32_t count)
{
    // Keep low-rate moves on the existing path. The margin covers the
    // requested high and low times plus a budget for DMA bus arbitration.
    return pulse == 144 && count >= 32 && period <= 720
        && period >= 2 * (pulse + M300_XY_DMA_EDGE_MARGIN);
}

void
m300_xy_dma_error_irq(void)
{
    if (DMA1->ISR & transfer_errors)
        shutdown("M300 XY DMA transfer error");
}

void
m300_xy_dma_init(void)
{
    enable_pclock((uint32_t)(uintptr_t)DMA1);
    for (unsigned i = 0; i < sizeof(axes) / sizeof(axes[0]); i++) {
        const struct xy_dma_axis *a = &axes[i];
        TIM_TypeDef *t = a->timer;
        enable_pclock((uint32_t)(uintptr_t)t);
        t->CR1 = t->CR2 = t->SMCR = t->DIER = t->CCER = 0;
        t->CCMR1 = t->CCMR2 = t->PSC = 0;
        a->rise->CCR = a->fall->CCR = 0;
        a->rise->CPAR = a->fall->CPAR = (uint32_t)(uintptr_t)&GPIOB->BSRR;
        a->rise->CMAR = (uint32_t)(uintptr_t)&a->high;
        a->fall->CMAR = (uint32_t)(uintptr_t)&a->low;
        DMA1->IFCR = a->flags;
    }
    armcm_enable_irq(m300_xy_dma_error_irq, DMA1_Channel2_IRQn, 1);
    armcm_enable_irq(m300_xy_dma_error_irq, DMA1_Channel3_IRQn, 1);
    armcm_enable_irq(m300_xy_dma_error_irq, DMA1_Channel6_IRQn, 1);
    armcm_enable_irq(m300_xy_dma_error_irq, DMA1_Channel7_IRQn, 1);
    initialized = 1;
}
DECL_INIT(m300_xy_dma_init);

uint32_t
m300_xy_dma_start(uint8_t axis, uint32_t period, uint32_t pulse,
                  uint32_t count, uint32_t first_clock)
{
    const struct xy_dma_axis *a = &axes[axis - 1];
    TIM_TypeDef *t = a->timer;
    m300_require_motion();
    if ((t->CR1 & TIM_CR1_CEN) || (GPIOB->ODR & a->high))
        shutdown("M300 XY DMA start with STEP active");

    t->DIER = 0;
    t->ARR = period - 1;
    *a->compare = pulse + M300_XY_DMA_EDGE_MARGIN;
    t->EGR = TIM_EGR_UG;
    t->SR = 0;
    DMA1->IFCR = a->flags;
    a->rise->CNDTR = a->fall->CNDTR = count;
    a->fall->CCR = a->rise->CCR = channel_mode | DMA_CCR_EN;
    t->DIER = TIM_DIER_UDE | a->compare_request;

    // Start close to the scheduled DWT deadline. Start after the compare
    // point in the initial cycle so the first DMA request is always a rise.
    uint32_t now = timer_read_time();
    int32_t delay = first_clock - now;
    if (delay < -(int32_t)timer_from_us(1000))
        shutdown("M300 XY DMA STEP start late");
    uint32_t lead = delay > 1 ? (uint32_t)delay : 1;
    if (lead >= period - *a->compare)
        shutdown("M300 XY DMA start outside timer window");
    t->CNT = period - lead;
    t->CR1 = TIM_CR1_URS | TIM_CR1_CEN;
    // Conservative upper bound on when the first timer update will occur.
    uint32_t first = timer_read_time() + lead;
    last_chained[axis - 1] = 0;
    return first;
}

uint32_t
m300_xy_dma_remaining(uint8_t axis)
{
    return axes[axis - 1].rise->CNDTR;
}

static uint32_t
stop_channels(const struct xy_dma_axis *a)
{
    a->timer->DIER = 0;
    a->timer->CR1 = 0;
    a->rise->CCR = a->fall->CCR = 0;
    // Observe the channel disables before reading the transfer count.
    (void)a->rise->CCR;
    (void)a->fall->CCR;
    return a->rise->CNDTR;
}

uint32_t
m300_xy_dma_stop(uint8_t axis)
{
    const struct xy_dma_axis *a = &axes[axis - 1];
    uint32_t remaining = stop_channels(a);
    if (GPIOB->ODR & a->high) {
        // A trigger stop may land immediately after a counted rising edge.
        // Hold that last pulse long enough for the driver to register it.
        uint32_t until = timer_read_time() + timer_from_us(2);
        while (timer_is_before(timer_read_time(), until))
            ;
    }
    GPIOB->BSRR = a->low;
    return remaining;
}

static void
report_completed_block(uint8_t axis, uint8_t chained)
{
    uint8_t mask = 1 << (axis - 1);
    if (chained)
        mask |= mask << 2;
    mask &= ~first_reported;
    if (mask) {
        first_reported |= mask;
        pending_report |= mask;
        sched_wake_task(&report_wake);
    }
}

uint8_t
m300_xy_dma_chain(uint8_t axis, uint32_t period, uint32_t count,
                  uint32_t last_rise_clock)
{
    const struct xy_dma_axis *a = &axes[axis - 1];
    TIM_TypeDef *t = a->timer;
    uint32_t old_period = t->ARR + 1;
    uint32_t limit = period < old_period ? period : old_period;
    if (a->rise->CNDTR || a->fall->CNDTR
        || (DMA1->ISR & a->flags & transfer_errors))
        return 0;
    m300_require_motion_gate();
    // A zero transfer count also persists after a missed overflow. The DWT
    // deadline rules out an older timer cycle before rearming the channels.
    if (!timer_is_before(timer_read_time(), last_rise_clock + limit))
        return 0;
    uint32_t counter = t->CNT;
    if (counter < *a->compare || counter + 64 >= limit)
        return 0;

    // ARR has no preload. Changing it after the final compare sets the gap
    // to the next rising edge without resetting CNT or shifting timer phase.
    // Keep requests masked while rearming the two finite channels.
    t->DIER = 0;
    t->SR = 0;
    t->ARR = period - 1;
    a->rise->CCR = a->fall->CCR = 0;
    DMA1->IFCR = a->flags;
    a->rise->CNDTR = a->fall->CNDTR = count;
    a->fall->CCR = a->rise->CCR = channel_mode | DMA_CCR_EN;
    uint32_t armed_counter = t->CNT;
    if (armed_counter < counter || armed_counter + 32 >= period
        || (t->SR & TIM_SR_UIF)) {
        // Requests stayed masked. Restore the completed transfer state so
        // the caller can stop this timer and use the regular handoff.
        a->rise->CCR = a->fall->CCR = 0;
        a->rise->CNDTR = a->fall->CNDTR = 0;
        return 0;
    }
    t->DIER = TIM_DIER_UDE | a->compare_request;
    last_chained[axis - 1] = 1;
    report_completed_block(axis, 1);
    return 1;
}

void
m300_xy_dma_finish(uint8_t axis, uint32_t deadline, uint32_t nominal_last)
{
    const struct xy_dma_axis *a = &axes[axis - 1];
    uint32_t remaining = m300_xy_dma_stop(axis);
    uint32_t falling = a->fall->CNDTR;
    uint32_t flags = DMA1->ISR & a->flags;
    if (remaining || falling || (flags & transfer_errors)) {
        // The counters and CNT are frozen. Capture them before the shutdown
        // hooks clear the DMA flags. Formatting runs after the guard closes.
        fault_snapshot.axis = axis;
        fault_snapshot.chained = last_chained[axis - 1];
        fault_snapshot.clock = timer_read_time();
        fault_snapshot.deadline = deadline;
        fault_snapshot.nominal_last = nominal_last;
        fault_snapshot.flags = flags;
        fault_snapshot.rise = remaining;
        fault_snapshot.fall = falling;
        fault_snapshot.counter = a->timer->CNT;
        fault_snapshot.period = a->timer->ARR + 1;
        fault_snapshot.compare = *a->compare;
        sched_wake_task(&report_wake);
        shutdown("M300 XY DMA incomplete STEP block");
    }
    report_completed_block(axis, 0);
}

void
m300_xy_dma_report_task(void)
{
    if (!sched_check_wake(&report_wake))
        return;
    irqstatus_t flag = irq_save();
    uint8_t report_mask = pending_report;
    pending_report = 0;
    irq_restore(flag);
    if (fault_snapshot.axis) {
        output("M300 XY DMA fault axis=%c chained=%c rise=%hu fall=%hu"
               " cnt=%hu period=%hu compare=%hu flags=%u"
               " clock=%u deadline=%u nominal_last=%u",
               fault_snapshot.axis, fault_snapshot.chained,
               fault_snapshot.rise, fault_snapshot.fall,
               fault_snapshot.counter, fault_snapshot.period,
               fault_snapshot.compare, fault_snapshot.flags,
               fault_snapshot.clock, fault_snapshot.deadline,
               fault_snapshot.nominal_last);
        fault_snapshot.axis = 0;
    }
    if (report_mask & 1)
        output("M300 XY STEP DMA completed first X block");
    if (report_mask & 2)
        output("M300 XY STEP DMA completed first Y block");
    if (report_mask & 4)
        output("M300 XY STEP DMA chained first X boundary");
    if (report_mask & 8)
        output("M300 XY STEP DMA chained first Y boundary");
}
DECL_TASK(m300_xy_dma_report_task);

void
m300_xy_dma_abort_all(void)
{
    if (initialized) {
        stop_channels(&axes[0]);
        stop_channels(&axes[1]);
        GPIOB->BSRR = axes[0].low | axes[1].low;
        DMA1->IFCR = axes[0].flags | axes[1].flags;
    }
}

// SPDX-License-Identifier: GPL-3.0-or-later
// Classic M300 SSD1322 and encoder. Private raw F103 GPIO ownership.
// No motion, heaters, Flash writes, bootloader API or SPI2 MISO ownership.
#ifndef M300_PANEL_TEST
#include <string.h>
#include "m300_uart.h"
#include "autoconf.h"
#include "board/io.h"
#include "board/armcm_boot.h"
#include "board/irq.h"
#include "board/misc.h"
#include "command.h"
#include "internal.h"
#include "sched.h"
#endif
#include "m300_sched.h"

DECL_CONSTANT_STR("RESERVE_PINS_m300_oled", "PB12,PB13,PB14,PB15,PE9,PE10");
DECL_CONSTANT_STR("RESERVE_PINS_m300_encoder", "PE7,PE8,PC5");
DECL_CONSTANT("M300_OLED_MAX_CHUNK", 32);
DECL_CONSTANT("M300_OLED_SPI_BURST_ABI", 1);
DECL_CONSTANT("M300_OLED_FAST_ABI", 1);
DECL_CONSTANT("M300_OLED_FAST_QUEUE", 4);
DECL_CONSTANT("M300_OLED_FAST_WIRE", 256);
DECL_CONSTANT("M300_PANEL_CAPTURE_ABI", 3);
DECL_CONSTANT("M300_PANEL_IRQ_PRIORITY", 3);
DECL_CONSTANT("M300_OLED_DMA_IRQ_PRIORITY", 4);
#define PANEL_EXTI_GROUP (31u << 5)
#define PANEL_EXTI_AB ((1u << 7) | (1u << 8))
DECL_CONSTANT("M300_LOCAL_OLED_ABI", 1);
DECL_CONSTANT_STR("M300_MCU_RELEASE", "0.13.14.6-FACTORY-INFO-UART8");
DECL_CONSTANT("M300_OLED_HOSTLINK_ABI", 1);
DECL_CONSTANT("M300_OLED_HOSTLINK_TIMEOUT_US", 1500000);
DECL_CONSTANT("M300_LOCAL_OLED_STARTUP_FIX", 1);
DECL_CONSTANT("M300_PANEL_POLL_US", 1000);
DECL_CONSTANT("M300_PANEL_REPORT_US", 20000);
DECL_CONSTANT("M300_PANEL_LONG_US", 600000);

static uint8_t oled_configured, panel_configured, panel_fault;
static uint32_t spi_cr1;
static uint32_t panel_spi_hz;
static void local_oled_init(void);
static void local_oled_cancel(void);
static void oled_dma_shutdown(void);
static uint8_t oled_dma_busy(void);
static int local_has_claim(void);
static void local_oled_recover(uint8_t reason, uint8_t timer_reset);
static void oled_host_shutdown(void);
static uint8_t oled_host_allowed(void);

static void
panel_put(GPIO_TypeDef *port, unsigned pin, unsigned value)
{
    writel((void *)&port->BSRR, (1u << pin) << (value ? 0 : 16));
}

static void
panel_mode(GPIO_TypeDef *port, unsigned pin, unsigned nibble)
{
    volatile uint32_t *reg = pin < 8 ? &port->CRL : &port->CRH;
    unsigned shift = (pin & 7) * 4;
    *reg = (*reg & ~(15u << shift)) | (nibble << shift);
}

static void
panel_output(GPIO_TypeDef *port, unsigned pin, unsigned value)
{
    panel_put(port, pin, value);  // latch BEFORE output mode: no transient pulse
    panel_mode(port, pin, 2);    // general-purpose push-pull, 2 MHz F103
}

static void
panel_pullup(GPIO_TypeDef *port, unsigned pin)
{
    panel_put(port, pin, 1);
    panel_mode(port, pin, 8);
}

void
m300_panel_init(void)
{
    RCC->APB2ENR |= (1u << 3) | (1u << 4) | (1u << 6); // B, C, E
    (void)RCC->APB2ENR;
    panel_output(GPIOE, 9, 0);
    panel_output(GPIOE, 10, 0);
    panel_output(GPIOB, 12, 1);
    panel_output(GPIOB, 14, 0);
    panel_pullup(GPIOE, 7);
    panel_pullup(GPIOE, 8);
    panel_pullup(GPIOC, 5);
    local_oled_init();
}
DECL_INIT(m300_panel_init);

void
m300_panel_shutdown(void)
{
    // A native clear_shutdown may clear the scheduler latch, but it must not
    // revive a previous display session. Only a complete MCU reset clears this.
    panel_fault = 1;
    EXTI->IMR &= ~((1u << 7) | (1u << 8));
    oled_dma_shutdown();
    oled_host_shutdown();
    // Only mark pending work here. The local Waiting/Shutdown screen is
    // rendered later by a bounded task, never from this shutdown/IRQ path.
    local_oled_recover(3, 1);
    // GPIO only: no timeout, ACK, host or display response in a fault path.
    RCC->APB2ENR |= (1u << 3) | (1u << 6);
    (void)RCC->APB2ENR;
    panel_put(GPIOB, 12, 1);
    panel_put(GPIOE, 9, 0);   // physically disable stale image on MCU shutdown
    panel_put(GPIOE, 10, 0);
}
DECL_SHUTDOWN(m300_panel_shutdown);

// One bounded contiguous SPI transfer, CS held LOW across the whole block.
// IRQs remain enabled. A single deadline bounds the ENTIRE operation.
static int
panel_spi_burst(uint8_t dc, const uint8_t *data, unsigned count)
{
    if ((panel_fault && !local_has_claim())
        || SPI2->CR1 != spi_cr1 || !count || count > 32)
        return 0;
    panel_put(GPIOB, 14, dc);
    panel_put(GPIOB, 12, 0);
    uint32_t deadline=timer_read_time()+timer_from_us(1000);
    for (unsigned i=0; i<count; i++) {
        while (!(SPI2->SR & (1u<<1)))
            if (!timer_is_before(timer_read_time(),deadline)) goto fail;
        writew((void *)&SPI2->DR,data[i]);
    }
    while ((SPI2->SR & ((1u<<1)|(1u<<7))) != (1u<<1))
        if (!timer_is_before(timer_read_time(),deadline)) goto fail;
    panel_put(GPIOB, 12, 1);
    return 1;
fail:
    panel_put(GPIOB, 12, 1);
    return 0;
}

static void
panel_spi_setup(uint32_t rate)
{
    // SPI2 is PRIVATE to this module. PB14 remains a GPIO D/C throughout.
    irqstatus_t flag = irq_save();
    RCC->APB1ENR |= 1u << 14;
    RCC->APB1RSTR |= 1u << 14;
    RCC->APB1RSTR &= ~(1u << 14);
    panel_mode(GPIOB, 13, 0xb);  // AF push-pull SCK, 50 MHz edge capability
    panel_mode(GPIOB, 15, 0xb);  // AF push-pull MOSI
    SPI2->CR1 = 0;
    SPI2->CR2 = 0;
    uint32_t pclk = get_pclock_frequency((uint32_t)SPI2), div = 0;
    while ((pclk >> (div + 1)) > rate && div < 7)
        div++;
    // Mode 0, MSB first, 8 bit, master, software NSS, one-line TX.
    spi_cr1 = (div << 3) | (1u << 2) | (1u << 6) | (1u << 8)
              | (1u << 9) | (1u << 14) | (1u << 15);
    SPI2->CR1 = spi_cr1;
    panel_spi_hz = pclk >> (div + 1);
    irq_restore(flag);
}

#include "m300_oled_dma.inc"
#include "m300_oled_local.inc"
#include "m300_oled_host.inc"

void
command_m300_oled_config(uint32_t *args)
{
    uint32_t rate=args[0];
    if (panel_fault || oled_configured || rate < 500000 || rate > 4500000)
        shutdown("M300 invalid OLED config");
    // Keep the local Waiting image and RESET level until first host operation.
    panel_spi_setup(rate);
    oled_configured=1;
}
DECL_COMMAND(command_m300_oled_config, "m300_oled_config rate=%u");

void
command_m300_oled_control(uint32_t *args)
{
    if (panel_fault || !oled_configured
        || args[1] > 1 || args[2] > 1)
        shutdown("M300 invalid OLED control");
    if (oled_display_fault)
        return;
    if (!oled_host_allowed())
        return;
    if (oled_dma_busy())
        shutdown("M300 invalid OLED control");
    local_oled_cancel();
    panel_put(GPIOB, 12, 1);
    panel_put(GPIOE, 10, args[1]);
    panel_put(GPIOE, 9, args[2]);
    sendf("m300_oled_ack token=%hu", args[0]);
}
DECL_COMMAND(command_m300_oled_control,
             "m300_oled_control token=%hu reset=%c gate=%c");

void
command_m300_oled_write(uint32_t *args)
{
    uint32_t dc = args[1], length = args[2];
    if (panel_fault || !oled_configured || dc > 1 || !length || length > 32)
        shutdown("M300 invalid OLED chunk");
    if (oled_display_fault)
        return;
    if (!oled_host_allowed())
        return;
    if (oled_dma_busy())
        shutdown("M300 OLED mixed legacy/DMA transaction");
    if (SPI2->CR1 != spi_cr1)
        shutdown("M300 OLED SPI ownership lost");
    uint8_t *data = command_decode_ptr(args[3]);
    local_oled_cancel();
    if (!panel_spi_burst(dc,data,length))
        shutdown("M300 OLED SPI timeout");
    sendf("m300_oled_ack token=%hu", args[0]);
}
DECL_COMMAND(command_m300_oled_write,
             "m300_oled_write token=%hu dc=%c data=%*s");

// Encoder samples are accumulated, never queued. One UART snapshot reports
// cumulative counters, so bounded delays cannot grow an input event queue.
static struct timer panel_timer;
static struct task_wake panel_wake;
static uint32_t poll_ticks, report_ticks, heartbeat_ticks, long_ticks;
static uint32_t last_report, press_time, position, presses, releases;
static uint32_t shorts, longs, invalid_transitions, panel_sequence;
// Raw position remains unchanged for the independent motion/deadman owner.
// Navigation commits only complete valid detents. An ambiguous AB jump clears
// just the unfinished detent, never already committed movement in this report.
static uint32_t nav_position;
static int8_t nav_partial;
static uint8_t nav_steps, panel_nav_enabled;
static uint8_t last_ab, pressed, candidate, debounce_count;
static uint8_t button_armed, long_sent;
static volatile uint8_t changed;

static uint8_t
panel_ab(void)
{
    return (GPIOE->IDR >> 7) & 3;
}

static void
panel_sample_ab(void)
{
    static const int8_t quadrature[16] = {
         0,  1, -1,  0, -1,  0,  0,  1,
         1,  0,  0, -1,  0, -1,  1,  0
    };
    uint8_t ab = panel_ab();
    if (ab != last_ab) {
        if ((ab ^ last_ab) == 3) {
            invalid_transitions++;
            nav_partial = 0;
        } else {
            int8_t step = quadrature[(last_ab << 2) | ab];
            position += step;
            nav_partial += step;
            if (nav_partial >= nav_steps) {
                nav_position += nav_steps;
                nav_partial = 0;
            } else if (nav_partial <= -(int8_t)nav_steps) {
                nav_position -= nav_steps;
                nav_partial = 0;
            }
        }
        last_ab = ab;
        changed = 1;
    }
}

// EXTI captures both edges at their source, including changes between 1ms
// button samples. No UART, allocation, SPI or event queue in this IRQ.
void
m300_encoder_irq(void)
{
    uint32_t pending = EXTI->PR & PANEL_EXTI_GROUP;
    // This private F103 profile is the sole owner of EXTI9_5. A stale enabled
    // line 5/6/9 must not leave the shared vector permanently asserted.
    EXTI->IMR &= ~(pending & ~PANEL_EXTI_AB);
    EXTI->PR = pending;
    if ((pending & PANEL_EXTI_AB) && panel_configured && !panel_fault)
        panel_sample_ab();
}

static void
panel_sample(uint32_t now)
{
    uint8_t raw_pressed = !(GPIOC->IDR & (1u << 5));
    if (candidate != raw_pressed) {
        candidate = raw_pressed;
        debounce_count = 1;
    } else if (debounce_count < 5) {
        debounce_count++;
    }
    if (debounce_count >= 5 && pressed != candidate) {
        pressed = candidate;
        changed = 1;
        if (pressed) {
            if (button_armed) {
                presses++;
                press_time = now;
                long_sent = 0;
            }
        } else {
            if (button_armed) {
                releases++;
                if (!long_sent)
                    shorts++;
            }
            // A button held during startup must be released before it can
            // produce a click/long event for a new host UI session.
            button_armed = 1;
            long_sent = 0;
        }
    }
    if (pressed && button_armed && !long_sent
        && (uint32_t)(now - press_time) >= long_ticks) {
        longs++;
        long_sent = 1;
        changed = 1;
    }
}

static uint_fast8_t
panel_event(struct timer *timer)
{
    uint32_t now = timer_read_time();
    panel_sample(now);
    uint32_t elapsed = now - last_report;
    if ((changed && elapsed >= report_ticks) || elapsed >= heartbeat_ticks) {
        last_report = now;
        changed = 0;
        sched_wake_task(&panel_wake);
    }
    timer->waketime = m300_next_timer(timer->waketime, timer_read_time(),
                                      poll_ticks);
    return SF_RESCHEDULE;
}

static void
panel_configure(uint8_t steps, uint8_t navigation)
{
    if (panel_fault || panel_configured)
        shutdown("M300 panel already configured");
    nav_steps = steps;
    panel_nav_enabled = navigation;
    nav_position = 0;
    nav_partial = 0;
    poll_ticks = timer_from_us(1000);
    report_ticks = timer_from_us(20000);
    heartbeat_ticks = timer_from_us(250000);
    long_ticks = timer_from_us(600000);
    last_ab = panel_ab();
    pressed = candidate = !(GPIOC->IDR & (1u << 5));
    button_armed = !pressed;
    debounce_count = 0;
    last_report = timer_read_time();
    panel_timer.func = panel_event;
    panel_timer.waketime = last_report + poll_ticks;
    panel_configured = 1;
    irqstatus_t flag = irq_save();
    EXTI->IMR &= ~PANEL_EXTI_GROUP;
    RCC->APB2ENR |= 1u; // AFIO clock; preserve SWJ/remap and unrelated EXTI
    AFIO->EXTICR[1] = (AFIO->EXTICR[1] & ~(15u << 12)) | (4u << 12);
    AFIO->EXTICR[2] = (AFIO->EXTICR[2] & ~15u) | 4u; // PE7 / PE8 only
    EXTI->RTSR = (EXTI->RTSR & ~PANEL_EXTI_GROUP) | PANEL_EXTI_AB;
    EXTI->FTSR = (EXTI->FTSR & ~PANEL_EXTI_GROUP) | PANEL_EXTI_AB;
    EXTI->PR = PANEL_EXTI_GROUP;
    NVIC_ClearPendingIRQ(EXTI9_5_IRQn);
    // Pinned armcm_timer sets SysTick to 2, UART is 0. Both preempt encoder 3.
    // Only EXTI writes its phase/position; the 1ms timer handles the button.
    armcm_enable_irq(m300_encoder_irq, EXTI9_5_IRQn, 3);
    EXTI->IMR |= (1u << 7) | (1u << 8);
    irq_restore(flag);
    sched_add_timer(&panel_timer);
}

void
command_m300_panel_config(uint32_t *args)
{
    (void)args;
    panel_configure(4, 0);
}
DECL_COMMAND(command_m300_panel_config, "m300_panel_config");

void
command_m300_panel_config_v2(uint32_t *args)
{
    uint32_t steps = args[0];
    if (steps != 1 && steps != 2 && steps != 4)
        shutdown("M300 invalid panel detent size");
    panel_configure(steps, 1);
}
DECL_COMMAND(command_m300_panel_config_v2, "m300_panel_config_v2 steps=%c");

static void
panel_send(void)
{
    irqstatus_t flag = irq_save();
    uint32_t seq = ++panel_sequence, pos = position, p = presses, r = releases;
    uint32_t s = shorts, l = longs, bad = invalid_transitions, nav = nav_position;
    uint8_t down = pressed;
    irq_restore(flag);
    if (panel_nav_enabled)
        sendf("m300_panel_state_v2 clock=%u sequence=%u position=%u pressed=%c"
              " presses=%u releases=%u shorts=%u longs=%u invalid=%u nav_position=%u",
              timer_read_time(), seq, pos, down, p, r, s, l, bad, nav);
    else
        sendf("m300_panel_state clock=%u sequence=%u position=%u pressed=%c"
              " presses=%u releases=%u shorts=%u longs=%u invalid=%u",
              timer_read_time(), seq, pos, down, p, r, s, l, bad);
}

void
command_m300_panel_query(uint32_t *args)
{
    (void)args;
    if (!panel_configured)
        shutdown("M300 panel not configured");
    panel_send();
}
DECL_COMMAND(command_m300_panel_query, "m300_panel_query");

void
m300_panel_task(void)
{
    if (sched_check_wake(&panel_wake))
        panel_send();
}
DECL_TASK(m300_panel_task);

// SPDX-License-Identifier: GPL-3.0-or-later
#line 1000 "m300_oled_dma.inc"
// Private SPI2 TX: STM32F103 DMA1 channel 5. Four fixed slots, no heap.
// Raw or lossless PackBits; 32 UART payload bytes -> <=256 SPI wire bytes.
// Other peripherals and the native Klipper step/ADC/safety paths are untouched.
#define OLED_QUEUE 4
#define OLED_WIRE 256
#define OLED_DMA_FLAGS (15u << 16)
static struct oled_slot {
    uint16_t token, length;
    uint8_t dc, data[OLED_WIRE];
} oled_slots[OLED_QUEUE];
static uint8_t oled_head, oled_count, oled_peak, oled_active;
static uint8_t oled_dma_initialized, oled_alarm_active, oled_display_fault;
static volatile uint8_t oled_dma_done, oled_dma_error;
static uint32_t oled_blocks, oled_wire_bytes, oled_started, oled_deadline;
static uint32_t oled_max_busy_ticks;
static struct task_wake oled_dma_wake;
static struct timer oled_dma_timer;

static uint8_t oled_dma_busy(void) { return oled_count; }

static uint_fast8_t
oled_dma_alarm(struct timer *timer)
{
    (void)timer;
    oled_alarm_active = 0;
    sched_wake_task(&oled_dma_wake);
    return SF_DONE;
}

static void
oled_dma_cancel_alarm(void)
{
    irqstatus_t flag = irq_save();
    if (oled_alarm_active) {
        sched_del_timer(&oled_dma_timer);
        oled_alarm_active = 0;
    }
    irq_restore(flag);
}

static void
oled_dma_alarm_at(uint32_t when)
{
    irqstatus_t flag = irq_save();
    if (oled_alarm_active)
        sched_del_timer(&oled_dma_timer);
    // The caller's timestamp can age while interrupts run or a timer is
    // removed. Read time inside this critical section and keep insertion
    // safely ahead of the native scheduler's current time.
    uint32_t minimum = timer_read_time() + timer_from_us(50);
    if (timer_is_before(when, minimum))
        when = minimum;
    oled_dma_timer.func = oled_dma_alarm;
    oled_dma_timer.waketime = when;
    oled_alarm_active = 1;
    sched_add_timer(&oled_dma_timer);
    irq_restore(flag);
}

void
m300_oled_dma_irq(void)
{
    uint32_t status = DMA1->ISR & OLED_DMA_FLAGS;
    if (!status)
        return;
    DMA1->IFCR = OLED_DMA_FLAGS;
    // Clearing EN stops further transfers, but SPI may still be shifting its
    // final bytes. The task ACKs only after TXE=1 and BSY=0, never in this IRQ.
    DMA1_Channel5->CCR = 0;
    if (status & (1u << 19)) oled_dma_error = 1;
    if (status & (1u << 17)) oled_dma_done = 1;
    sched_wake_task(&oled_dma_wake);
}

static void
oled_dma_shutdown(void)
{
    if (oled_dma_initialized) {
        SPI2->CR2 &= ~(1u << 1); // TXDMAEN
        DMA1_Channel5->CCR = 0;
        DMA1->IFCR = OLED_DMA_FLAGS;
    }
    oled_active = oled_count = 0;
    oled_dma_done = oled_dma_error = 0;
    oled_alarm_active = 0;
    // No timer deletion, ACK or wait inside DECL_SHUTDOWN/IRQ context.
}

static void
oled_dma_fail(void)
{
    oled_display_fault = 1;
    oled_dma_cancel_alarm();
    oled_dma_shutdown();
    panel_put(GPIOB, 12, 1);
    panel_put(GPIOE, 9, 0);
    panel_put(GPIOE, 10, 0);
    // An optional display DMA/BSY timeout does not shut down a print.
    // Do not ACK uncompleted operations. Fault remains latched until reset.
}

void
m300_oled_dma_task(void)
{
    if (!sched_check_wake(&oled_dma_wake) || panel_fault || !oled_host_allowed())
        return;
    if (oled_display_fault)
        return;
    uint32_t now = timer_read_time();
    if (oled_active) {
        if (oled_dma_error || SPI2->CR1 != spi_cr1) {
            oled_dma_fail();
            return;
        }
        if (!oled_dma_done || (SPI2->SR & ((1u << 1) | (1u << 7))) != (1u << 1)) {
            if (!timer_is_before(now, oled_deadline))
                oled_dma_fail();
            else if (oled_dma_done)
                oled_dma_alarm_at(now + timer_from_us(10));
            return;
        }
        SPI2->CR2 &= ~(1u << 1);
        DMA1_Channel5->CCR = 0;
        oled_dma_cancel_alarm();
        panel_put(GPIOB, 12, 1);
        struct oled_slot *s = &oled_slots[oled_head];
        uint32_t duration = now - oled_started;
        if (duration > oled_max_busy_ticks) oled_max_busy_ticks = duration;
        oled_blocks++;
        oled_wire_bytes += s->length;
        oled_head = (oled_head + 1) % OLED_QUEUE;
        oled_count--;
        oled_active = 0;
        sendf("m300_oled_ack token=%hu", s->token);
    }
    if (!oled_count)
        return;
    if (SPI2->CR1 != spi_cr1) {
        oled_dma_fail();
        return;
    }
    if (!oled_dma_initialized) {
        RCC->AHBENR |= 1u;
        (void)RCC->AHBENR;
        DMA1_Channel5->CCR = 0;
        DMA1->IFCR = OLED_DMA_FLAGS;
        NVIC_ClearPendingIRQ(DMA1_Channel5_IRQn);
        // SysTick/step scheduler is priority 2 in the pinned upstream.
        armcm_enable_irq(m300_oled_dma_irq, DMA1_Channel5_IRQn, 4);
        oled_dma_initialized = 1;
    }
    struct oled_slot *s = &oled_slots[oled_head];
    oled_started = now;
    oled_deadline = now + timer_from_us(2000u + (s->length * 8000000u / panel_spi_hz));
    oled_dma_done = oled_dma_error = 0;
    DMA1_Channel5->CCR = 0;
    DMA1->IFCR = OLED_DMA_FLAGS;
    DMA1_Channel5->CPAR = (uint32_t)(uintptr_t)&SPI2->DR;
    DMA1_Channel5->CMAR = (uint32_t)(uintptr_t)s->data;
    DMA1_Channel5->CNDTR = s->length;
    panel_put(GPIOB, 14, s->dc);
    panel_put(GPIOB, 12, 0);
    oled_active = 1;
    __DMB();
    // Byte-width memory/peripheral, MINC, memory->peripheral, low priority.
    // SPI2 never enables RXDMA or claims PB14 as MISO.
    SPI2->CR2 |= 1u << 1;
    DMA1_Channel5->CCR = (1u << 7) | (1u << 4) | (1u << 3) | (1u << 1) | 1u;
    oled_dma_alarm_at(oled_deadline);
}
DECL_TASK(m300_oled_dma_task);

void
command_m300_oled_burst(uint32_t *args)
{
    uint32_t dc=args[1], encoding=args[2], length=args[3], size=args[4];
    if (panel_fault || !oled_configured || dc > 1 || encoding > 1
        || !length || length > OLED_WIRE || !size || size > 32
        || (!encoding && length != size))
        shutdown("M300 invalid OLED DMA block");
    if (oled_display_fault)
        return; // latched optional fault: no SPI, ACK, power-up or print stop
    if (!oled_host_allowed())
        return; // late background data cannot overwrite local Waiting
    if (oled_count >= OLED_QUEUE)
        shutdown("M300 OLED DMA queue overflow");
    struct oled_slot *s = &oled_slots[(oled_head + oled_count) % OLED_QUEUE];
    uint8_t *data = command_decode_ptr(args[5]);
    unsigned out=0;
    if (!encoding) {
        memcpy(s->data, data, size);
        out = size;
    } else {
        for (unsigned i=0; i<size;) {
            uint8_t code=data[i++];
            unsigned count=(code & 127u) + 1;
            if (count > length - out || i >= size)
                shutdown("M300 invalid OLED RLE size");
            if (code & 128u) {
                memset(s->data + out, data[i++], count);
            } else {
                if (count > size - i)
                    shutdown("M300 invalid OLED RLE literal");
                memcpy(s->data + out, data + i, count);
                i += count;
            }
            out += count;
        }
    }
    if (out != length)
        shutdown("M300 incomplete OLED RLE block");
    s->token = args[0]; s->length = out; s->dc = dc;
    local_oled_cancel();
    oled_count++;
    if (oled_count > oled_peak) oled_peak=oled_count;
    sched_wake_task(&oled_dma_wake);
}
DECL_COMMAND(command_m300_oled_burst,
             "m300_oled_burst token=%hu dc=%c encoding=%c length=%hu data=%*s");

void
command_m300_oled_stats(uint32_t *args)
{
    (void)args;
    sendf("m300_oled_stats blocks=%u wire=%u queued=%c peak=%c fault=%c spi_hz=%u max_busy_ticks=%u",
          oled_blocks, oled_wire_bytes, oled_count, oled_peak,
          oled_display_fault, panel_spi_hz, oled_max_busy_ticks);
}
DECL_COMMAND(command_m300_oled_stats, "m300_oled_query_stats");

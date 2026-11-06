// Common fault indication on the audited RGB pins. GPL-3.0-or-later.
// The permanent scheduler task wake survives shutdown's user-timer reset.
// No UART traffic, new timer IRQ, actuator access or fault clearing is needed.
#define STATUS_LED_STEP_US 5000000u
static volatile uint8_t status_led_error_active, status_led_error_phase;
static uint32_t status_led_error_since;

static void
status_led_apply(void)
{
    raw_output(GPIOD, 7, status_led_error_phase == 0); // red
    raw_output(GPIOB, 5, status_led_error_phase == 1); // green
    raw_output(GPIOD, 6, status_led_error_phase == 2); // blue
}

static void
status_led_error_start(void)
{
    if (!status_led_error_active) {
        status_led_error_active = 1;
        status_led_error_phase = 0;
        status_led_error_since = timer_read_time();
    }
    status_led_apply();
}

void
m300_status_led_task(void)
{
    if (!status_led_error_active)
        return;
    irqstatus_t flag = irq_save();
    uint32_t now = timer_read_time();
    uint32_t elapsed = now - status_led_error_since;
    uint32_t step = timer_from_us(STATUS_LED_STEP_US);
    if (elapsed >= step) {
        uint32_t phases = elapsed / step;
        status_led_error_phase = (status_led_error_phase + phases) % 3;
        status_led_error_since += phases * step;
        status_led_apply();
    }
    irq_restore(flag);
}
DECL_TASK(m300_status_led_task);

static uint32_t
status_led_filter(void *regs, uint32_t bit, uint32_t value)
{
    // Generic GPIO shutdown/default writes cannot blank a latched alarm.
    // The buzzer and every non-RGB output retain their existing policy.
    if (status_led_error_active) {
        if (regs == GPIOD && bit == (1u << 7))
            return status_led_error_phase == 0;
        if (regs == GPIOB && bit == (1u << 5))
            return status_led_error_phase == 1;
        if (regs == GPIOD && bit == (1u << 6))
            return status_led_error_phase == 2;
    }
    return value;
}

// Classic Zortrax M300, STM32F103: P01 local safety and fixed board resources.
//
// Copyright (C) 2026 M300 port contributors
// This file may be distributed under the terms of the GNU GPLv3 license.
// Board facts: project classic-M300 firmware/GPIO audit, MAPA_IO.json.
// Architecture informed by the project's Inventure guard; no F207 registers,
// shared-extruder topology, ADC3, chamber control or Inventure ABI is used.

#include "autoconf.h"
#include "board/irq.h"
#include "board/misc.h"
#include "command.h"
#include "internal.h"
#include "m300.h"
#include "m300_errors.h"
#if CONFIG_M300_XY_STEP_TIMER
#include "m300_xy_step_timer.h"
#endif
#include "sched.h"
#include "m300_sched.h"

#if !CONFIG_MACH_STM32F103 || CONFIG_CLOCK_FREQ != 72000000
#error "M300 P01 requires the STM32F103 / 72 MHz profile"
#endif
#if CONFIG_FLASH_APPLICATION_ADDRESS != 0x08008000
#error "M300 P01 application must start at 0x08008000"
#endif
#if CONFIG_FLASH_APPLICATION_ADDRESS + CONFIG_FLASH_SIZE > 0x0803a000
#error "M300 P01 application region overlaps protected stock flash"
#endif
#if CONFIG_RAM_SIZE > 0x5000
#error "M300 P01 uses the conservative 20 KiB SRAM build profile"
#endif
#if !CONFIG_STM32_SERIAL_USART1 || CONFIG_STM32F103GD_DISABLE_SWD
#error "M300 P01 requires USART1 PA9/PA10 and preserved SWD"
#endif
#if CONFIG_WANT_SPI || CONFIG_WANT_I2C || CONFIG_WANT_HARD_PWM \
    || CONFIG_WANT_SOFTWARE_SPI || CONFIG_WANT_SOFTWARE_I2C
#error "M300 P01 has private panel SPI2 and native software PWM only"
#endif
#if CONFIG_WANT_BUTTONS || CONFIG_WANT_TMCUART || CONFIG_WANT_NEOPIXEL \
    || CONFIG_WANT_PULSE_COUNTER || CONFIG_WANT_ST7920 || CONFIG_WANT_HD44780 \
    || CONFIG_WANT_HX71X || CONFIG_WANT_CS1237 || CONFIG_WANT_TRIGGER_ANALOG
#error "M300 P01 excludes unaudited alternate GPIO peripheral drivers"
#endif

DECL_CONSTANT("M300_ABI", M300_ABI);
DECL_CONSTANT("M300_ARM_MAGIC", M300_ARM_MAGIC);
DECL_CONSTANT("M300_HOT_RAW_MAX", M300_HOT_RAW_MAX);
DECL_CONSTANT("M300_BED_RAW_MIN", M300_BED_RAW_MIN);
DECL_CONSTANT("M300_BED_RAW_MAX", M300_BED_RAW_MAX);
DECL_CONSTANT_STR("M300_MODEL", "M300_CLASSIC");
DECL_CONSTANT_STR("M300_STAGE", "P01_LAB");
DECL_CONSTANT("M300_SOFTWARE_PWM_ONLY", 1);
DECL_CONSTANT("M300_FAN_POLICY", 3);
DECL_CONSTANT("M300_LOCAL_COOLING_ABI", 1);
DECL_CONSTANT("M300_LOCAL_COOLING_ON_RAW", 314);
DECL_CONSTANT("M300_LOCAL_COOLING_OFF_RAW", 281);
DECL_CONSTANT("M300_STATUS_LED_ABI", 1);
DECL_CONSTANT("M300_STATUS_LED_ERROR_STEP_US", 5000000);
DECL_CONSTANT_STR("M300_OUTPUT_MODE", "SOFTWARE_PWM_ONLY");

#define GUARD_US 10000
#define FRESH_US 1000000
#define ADC_HOT 1
#define ADC_BED 2
#define ADC_BOTH (ADC_HOT | ADC_BED)

// This indirection lets the native C register model emulate atomic BSRR writes.
// In firmware it is exactly one volatile peripheral write (no ODR read/modify).
#ifndef M300_WRITE_BSRR
#define M300_WRITE_BSRR(regs, value) ((regs)->BSRR = (value))
#endif

static volatile uint8_t configured, armed, fault, gates, heartbeat_seen;
static volatile uint8_t adc_seen;
static volatile uint16_t hot_raw, bed_raw;
static volatile uint32_t hot_time, bed_time, heartbeat_time;
static uint16_t hot_min, hot_max, bed_min, bed_max;
// Shadow the logical fan GPIO level even while protective cooling overrides it.
// This is also the source of truth for toggles while the physical pin is HIGH.
static volatile uint8_t fan_requested = 3;
static volatile uint8_t fan_forced = 1;

int
m300_factory_write_allowed(void)
{
    // Flash reads/IRQ service can stall while the FPEC is busy. The write
    // window ends before board config; also check the three physical gates.
    return !configured && !armed && !fault && !sched_is_shutdown()
        && !(GPIOD->ODR & (1u << 14)) && !(GPIOC->ODR & (3u << 8))
        && !(GPIOE->IDR & (1u << 15));
}

static void
raw_write(GPIO_TypeDef *regs, uint32_t bit, uint32_t value)
{
    M300_WRITE_BSRR(regs, value ? bit : bit << 16);
}

static void
raw_mode(GPIO_TypeDef *regs, unsigned pin, unsigned nibble)
{
    unsigned shift = (pin & 7) * 4;
    volatile uint32_t *cr = pin < 8 ? &regs->CRL : &regs->CRH;
    *cr = (*cr & ~(0xfu << shift)) | (nibble << shift);
}

static void
raw_output(GPIO_TypeDef *regs, unsigned pin, unsigned value)
{
    raw_write(regs, 1u << pin, value);
    raw_mode(regs, pin, 0x2); // F103 MODE=10 (2 MHz), CNF=00 push-pull
}

static void
raw_pullup(GPIO_TypeDef *regs, unsigned pin)
{
    raw_write(regs, 1u << pin, 1);
    raw_mode(regs, pin, 0x8); // F103 input with ODR-selected pull-up
}

#include "m300_status_led.inc"

static void
raw_safe_outputs(void)
{
    RCC->APB2ENR |= RCC_APB2ENR_IOPAEN | RCC_APB2ENR_IOPBEN
        | RCC_APB2ENR_IOPCEN | RCC_APB2ENR_IOPDEN | RCC_APB2ENR_IOPEEN;
    (void)RCC->APB2ENR;
    // Disable the common motor driver gate before changing STEP/MS outputs.
    raw_output(GPIOD, 14, 0);
    raw_output(GPIOC, 8, 0);
    raw_output(GPIOC, 9, 0);
    raw_output(GPIOB, 3, 0);
    raw_output(GPIOB, 4, 0);
    raw_output(GPIOB, 7, 0);
    raw_output(GPIOA, 0, 0);
    raw_output(GPIOD, 9, 0);
    raw_output(GPIOD, 13, 0);
    raw_output(GPIOC, 12, 0);
    raw_output(GPIOD, 0, 0);

    // Audited stock profile: X=HHH, Y=HHH, Z=LLH. E has no proven MS GPIO.
    raw_output(GPIOB, 10, 1);
    raw_output(GPIOB, 11, 1);
    raw_output(GPIOD, 8, 1);
    raw_output(GPIOD, 10, 1);
    raw_output(GPIOD, 11, 1);
    raw_output(GPIOD, 12, 1);
    raw_output(GPIOA, 15, 0);
    raw_output(GPIOC, 10, 0);
    raw_output(GPIOC, 11, 1);

    // Unknown startup/shutdown thermal state: retain protective cooling.
    raw_output(GPIOE, 13, 1);
    raw_output(GPIOE, 14, 1);
    fan_forced = 1;
    // Blank stale OLED content electrically; panel owns SPI2 and later startup.
    raw_output(GPIOB, 12, 1);
    raw_output(GPIOE, 9, 0);
    raw_output(GPIOE, 10, 0);
}

void
m300_early_init(void)
{
    // Called after the F103 peripheral clock reset, before PLL lock/setup.
    // Does not use timers, heap, GPIO helpers, SPI, ADC, or initialized clocks.
    raw_safe_outputs();
    raw_pullup(GPIOE, 15); // Open connector = HIGH = fault, never floating-safe.
    raw_pullup(GPIOD, 5);
    raw_pullup(GPIOD, 1);
    raw_pullup(GPIOE, 7);
    raw_pullup(GPIOE, 8);
    raw_pullup(GPIOC, 5);
}

static void
force_safe(void)
{
#if CONFIG_M300_XY_STEP_TIMER
    irqstatus_t flag = irq_save();
#endif
    armed = 0;
#if CONFIG_M300_XY_STEP_TIMER
    raw_write(GPIOD, 1u << 14, 0);
    m300_xy_timer_abort_all();
#endif
    raw_safe_outputs();
#if CONFIG_M300_XY_STEP_TIMER
    irq_restore(flag);
#endif
}

static void capture_guard_error(uint8_t reason);

static void
trip(uint8_t reason)
{
    if (!fault) {
        fault = reason;
        capture_guard_error(reason);
    }
    force_safe();
    shutdown("M300 local guard latched");
}

static uint16_t
read_inputs(void)
{
    uint32_t e = GPIOE->IDR, d = GPIOD->IDR, c = GPIOC->IDR;
    return (!!(e & (1u << 15)) << 0)
        | (!!(d & (1u << 5)) << 1)
        | (!!(d & (1u << 1)) << 2)
        | (!!(e & (1u << 7)) << 3)
        | (!!(e & (1u << 8)) << 4)
        | (!!(c & (1u << 5)) << 5);
}

static uint8_t
is_fresh(uint32_t now, uint32_t stamp)
{
    // Unsigned elapsed time supports CYCCNT wrap; armed checks run every 10 ms.
    return (uint32_t)(now - stamp) < timer_from_us(FRESH_US);
}

static void
capture_guard_error(uint8_t reason)
{
    uint16_t code = 0;
    uint8_t kind = M300_ERROR_GUARD;
    if (reason == M300_FAULT_PLATFORM)
        kind = M300_ERROR_PLATFORM; // PE15 does not identify small vs large.
    else if (reason == M300_FAULT_HEARTBEAT)
        kind = M300_ERROR_LINK;
    else if (reason == M300_FAULT_ADC_STALE) {
        uint32_t now = timer_read_time();
        uint8_t hot_bad = !(adc_seen & ADC_HOT) || !is_fresh(now, hot_time);
        uint8_t bed_bad = !(adc_seen & ADC_BED) || !is_fresh(now, bed_time);
        kind = M300_ERROR_SENSOR;
        code = hot_bad != bed_bad ? (hot_bad ? 15 : 14) : 0;
    } else if (reason == M300_FAULT_ADC_RANGE) {
        kind = M300_ERROR_SENSOR;
        // ADC rails / stale data are sensor faults, never proof of overheat.
        if (hot_raw == 0 || hot_raw >= 4095)
            code = 15;
        else if (bed_raw == 0 || bed_raw >= 4095)
            code = 14;
        else if (hot_raw < hot_min || hot_raw > hot_max)
            code = hot_raw > hot_max ? 11 : 15;
        else if (bed_raw < bed_min || bed_raw > bed_max)
            code = bed_raw < bed_min ? 12 : 14;
    }
    m300_error_capture(code, kind);
}

void
m300_error_adc(void *adc, uint32_t channel)
{
    // Native ADC range failures may also occur before ARM. Do not add an
    // ADC owner or change any native sample/range-check limit.
    if (adc == ADC1 && (channel == 8 || channel == 9))
        m300_error_capture(channel == 9 ? 15 : 14, M300_ERROR_SENSOR);
}

static uint8_t
raw_in_range(void)
{
    return hot_raw >= hot_min && hot_raw <= hot_max
        && bed_raw >= bed_min && bed_raw <= bed_max;
}

static uint8_t
fan_control_allowed(uint32_t now)
{
    // Fan PWM is independent of motion/heating ARM permissions. It still
    // requires an acknowledged configuration, live host and valid native ADC.
    return configured && !fault && !sched_is_shutdown() && heartbeat_seen
        && is_fresh(now, heartbeat_time) && adc_seen == ADC_BOTH
        && is_fresh(now, hot_time) && is_fresh(now, bed_time) && raw_in_range();
}

#include "m300_cooling.inc"

static void
sync_fan_policy(void)
{
    irqstatus_t flag = irq_save();
    uint32_t now = timer_read_time();
    uint8_t old_mode = cool_mode, old_levels = cool_levels;
    cooling_policy(now);
    fan_forced = cool_mode != COOL_NATIVE;
    // A local thermostat change must reach the pins even while the override
    // boolean remains true. Native levels are restored on healthy handover.
    uint8_t physical = ((GPIOE->ODR >> 13) & 3u);
    if (old_mode != cool_mode || (fan_forced && (old_levels != cool_levels || physical != cool_levels))) {
        uint8_t levels = fan_forced ? cool_levels : fan_requested;
        raw_write(GPIOE, 1u << 13, levels & 1);
        raw_write(GPIOE, 1u << 14, levels & 2);
    }
    irq_restore(flag);
}

static void
guard_check(void)
{
    // Read the clock and all mutable sample stamps in the same IRQ snapshot.
    // An ADC interrupt between a caller's clock read and these stamp reads
    // can otherwise make now-stamp wrap to ~UINT32_MAX and falsely expire
    // a sample which was JUST acquired. Keep the one-second deadline intact.
    irqstatus_t flag = irq_save();
    uint32_t now = timer_read_time();
    if (fault)
        goto done;
    // PE15 is an independent local latch, including during an unarmed session.
    if (GPIOE->IDR & (1u << 15))
        trip(M300_FAULT_PLATFORM);
    if (!armed) {
        // Do not let ancient samples appear fresh again after CYCCNT wraps.
        if ((adc_seen & ADC_HOT) && !is_fresh(now, hot_time))
            adc_seen &= ~ADC_HOT;
        if ((adc_seen & ADC_BED) && !is_fresh(now, bed_time))
            adc_seen &= ~ADC_BED;
        if (heartbeat_seen && !is_fresh(now, heartbeat_time))
            heartbeat_seen = 0;
        goto done;
    }
    if (!heartbeat_seen || !is_fresh(now, heartbeat_time))
        trip(M300_FAULT_HEARTBEAT);
    if (adc_seen != ADC_BOTH || !is_fresh(now, hot_time)
        || !is_fresh(now, bed_time))
        trip(M300_FAULT_ADC_STALE);
    if (!raw_in_range())
        trip(M300_FAULT_ADC_RANGE);
done:
    irq_restore(flag);
}

static uint_fast8_t
guard_event(struct timer *timer)
{
    guard_check();
    sync_fan_policy();
    timer->waketime = m300_next_timer(timer->waketime, timer_read_time(),
                                      timer_from_us(GUARD_US));
    return SF_RESCHEDULE;
}

static struct timer guard_timer = { .func = guard_event };
static uint8_t guard_timer_started;

void
m300_board_init(void)
{
    // Generic timer_init() is later in DECL_INIT and resets CYCCNT.
    // Early GPIO protection is already active from m300_early_init().
    guard_timer_started=0;
    status_led_error_active = status_led_error_phase = 0;
}
DECL_INIT(m300_board_init);

void
m300_guard_start_task(void)
{
    if(guard_timer_started)return;
    guard_timer_started=1;
    guard_timer.waketime = timer_read_time() + timer_from_us(GUARD_US);
    sched_add_timer(&guard_timer);
}
DECL_TASK(m300_guard_start_task);

void
m300_board_shutdown(void)
{
    if (!fault)
        fault = M300_FAULT_SHUTDOWN;
    force_safe();
    status_led_error_start();
}
DECL_SHUTDOWN(m300_board_shutdown);

enum pin_role {
    PIN_FORBIDDEN, PIN_MOTION, PIN_HEAT, PIN_FAN, PIN_AUX,
    PIN_INPUT, PIN_ADC, PIN_UART_TX, PIN_UART_RX,
};

static enum pin_role
pin_role(uint32_t pin)
{
    switch (pin) {
    case GPIO('B', 3): case GPIO('B', 4): case GPIO('B', 7):
    case GPIO('A', 0): case GPIO('D', 9): case GPIO('D', 13):
    case GPIO('C', 12): case GPIO('D', 0): case GPIO('D', 14):
        return PIN_MOTION;
    case GPIO('C', 8): case GPIO('C', 9):
        return PIN_HEAT;
    case GPIO('E', 13): case GPIO('E', 14):
        return PIN_FAN;
    case GPIO('D', 7): case GPIO('B', 5): case GPIO('D', 6):
    case GPIO('C', 4):
        return PIN_AUX;
    case GPIO('E', 12): case GPIO('C', 6): case GPIO('C', 7):
        return PIN_INPUT;
    case GPIO('B', 0): case GPIO('B', 1):
        return PIN_ADC;
    case GPIO('A', 9):
        return PIN_UART_TX;
    case GPIO('A', 10):
        return PIN_UART_RX;
    default:
        // Includes private MS/PE15/PD1/PD5/OLED/encoder, SWD, SD and unknowns.
        return PIN_FORBIDDEN;
    }
}

static uint32_t
pin_from_regs(void *regs, uint32_t bit)
{
    if (!bit || (bit & (bit - 1)) || bit > (1u << 15))
        trip(M300_FAULT_PIN);
    uint32_t port;
    if (regs == GPIOA) port = 0;
    else if (regs == GPIOB) port = 1;
    else if (regs == GPIOC) port = 2;
    else if (regs == GPIOD) port = 3;
    else if (regs == GPIOE) port = 4;
    else { trip(M300_FAULT_PIN); return 0; }
    return port * 16 + __builtin_ctz(bit);
}

void
m300_check_pin_mode(uint32_t pin, uint32_t mode)
{
    enum pin_role role = pin_role(pin);
    if ((role == PIN_UART_TX || role == PIN_UART_RX)
        && mode == GPIO_FUNCTION(7))
        return;
    if (role == PIN_INPUT && mode == GPIO_INPUT)
        return;
    if (role == PIN_ADC && mode == GPIO_ANALOG)
        return;
    if (role >= PIN_MOTION && role <= PIN_AUX && mode == GPIO_OUTPUT)
        return;
    // This rejects all timer AF/HW PWM, native SPI/I2C, private pin takeovers,
    // ADC repurposing and accidental SWD disable before GPIO mode can change.
    trip(M300_FAULT_PIN);
}

void
m300_check_native_input(uint32_t pin)
{
    if (pin_role(pin) != PIN_INPUT)
        trip(M300_FAULT_PIN);
}

static uint8_t
gate_open(uint8_t gate)
{
    return armed && !fault && !sched_is_shutdown() && (gates & gate);
}

uint32_t
m300_filter_gpio(void *regs, uint32_t bit, uint32_t val)
{
    enum pin_role role = pin_role(pin_from_regs(regs, bit));
    val = !!val;
    if (role == PIN_MOTION)
        return gate_open(M300_GATE_MOTION) ? val : 0;
    if (role == PIN_HEAT)
        return gate_open(M300_GATE_HEAT) ? val : 0;
    if (role == PIN_FAN) {
        unsigned mask = bit == (1u << 13) ? 1 : 2;
        fan_requested = (fan_requested & ~mask) | (val ? mask : 0);
        sync_fan_policy();
        return fan_forced ? !!(cool_levels & mask) : val;
    }
    if (role == PIN_AUX)
        return status_led_filter(regs, bit, val);
    trip(M300_FAULT_PIN);
    return 0;
}

uint32_t
m300_toggle_gpio(void *regs, uint32_t bit)
{
    // STEP is the highest-rate path. These four exact, single-bit outputs
    // have already passed native GPIO mode/configuration ownership checks.
    // Preserve the same live gate test on EVERY edge, but avoid decoding a
    // port/pin number and running the general role classifier for each STEP.
    // No direction, enable, heater, fan, auxiliary or unknown pin takes this
    // path; they retain the general guard below.
    if ((regs == GPIOB && (bit == (1u << 3) || bit == (1u << 4)
                          || bit == (1u << 7)))
        || (regs == GPIOA && bit == (1u << 0)))
        return gate_open(M300_GATE_MOTION)
            ? !(((GPIO_TypeDef *)regs)->ODR & bit) : 0;
    uint32_t val;
    if (regs == GPIOE && (bit == (1u << 13) || bit == (1u << 14))) {
        unsigned mask = bit == (1u << 13) ? 1 : 2;
        val = !(fan_requested & mask);
    } else {
        val = !(((GPIO_TypeDef *)regs)->ODR & bit);
    }
    return m300_filter_gpio(regs, bit, val);
}

void
m300_require_motion(void)
{
    guard_check();
    if (!gate_open(M300_GATE_MOTION))
        trip(M300_FAULT_REQUEST);
}

#if CONFIG_M300_XY_STEP_TIMER
void
m300_require_motion_gate(void)
{
    // Continuing an active timer uses the live motion gate. The periodic
    // guard still checks ADC and host freshness and aborts any active STEP timer.
    if (GPIOE->IDR & (1u << 15))
        trip(M300_FAULT_PLATFORM);
    if (!gate_open(M300_GATE_MOTION))
        trip(M300_FAULT_REQUEST);
}
#endif

void
m300_require_output(void *regs, uint32_t bit, uint32_t on)
{
    if (!on)
        return;
    enum pin_role role = pin_role(pin_from_regs(regs, bit));
    if (role == PIN_MOTION)
        m300_require_motion();
    else if (role == PIN_HEAT) {
        guard_check();
        if (!gate_open(M300_GATE_HEAT))
            trip(M300_FAULT_REQUEST);
    }
}

void
m300_check_output_defaults(uint32_t pin, uint32_t value, uint32_t default_value)
{
    enum pin_role role = pin_role(pin);
    if ((role == PIN_MOTION || role == PIN_HEAT) && (value || default_value))
        trip(M300_FAULT_CONFIG);
}

void
m300_adc_observe(void *adc, uint32_t channel, uint16_t value)
{
    // Native Klipper uses ADC1 for both PB0/CH8 and PB1/CH9. The original
    // firmware's ADC2 hotend selection is not a requirement of the board.
    if (adc != ADC1 || (channel != 8 && channel != 9))
        return;
    irqstatus_t flag = irq_save();
    uint32_t now = timer_read_time();
    // A delayed conversion may not revive a session whose local deadline passed.
    if (armed)
        guard_check();
    if (channel == 9) {
        hot_raw = value;
        hot_time = now;
        adc_seen |= ADC_HOT;
        cool_native_seen |= ADC_HOT;
    } else {
        bed_raw = value;
        bed_time = now;
        adc_seen |= ADC_BED;
        cool_native_seen |= ADC_BED;
    }
    if (armed && (value == 0 || value >= 4095 || !raw_in_range()))
        trip(M300_FAULT_ADC_RANGE);
    irq_restore(flag);
}

static void
send_state(void)
{
    irqstatus_t flag = irq_save();
    uint32_t now = timer_read_time();
    sync_fan_policy();
    uint8_t c = configured, a = armed, f = fault, g = gates, seen = adc_seen;
    uint16_t h = hot_raw, b = bed_raw, inputs = read_inputs();
    uint32_t ha = seen & ADC_HOT ? now - hot_time : UINT32_MAX;
    uint32_t ba = seen & ADC_BED ? now - bed_time : UINT32_MAX;
    uint32_t hb = heartbeat_seen ? now - heartbeat_time : UINT32_MAX;
    uint8_t cooling = fan_forced;
    irq_restore(flag);
    sendf("m300_state clock=%u configured=%c armed=%c fault=%c gates=%c"
          " inputs=%hu adc_seen=%c hot_raw=%hu bed_raw=%hu hot_age=%u"
          " bed_age=%u heartbeat_age=%u forced_cooling=%c",
          now, c, a, f, g, inputs, seen, h, b, ha, ba, hb, cooling);
}

void
command_m300_config(uint32_t *args)
{
    if (configured || armed || fault || (args[0] & ~3u)
        || !args[1] || args[1] >= args[2] || args[2] > M300_HOT_RAW_MAX
        || args[3] < M300_BED_RAW_MIN || args[3] >= args[4]
        || args[4] > M300_BED_RAW_MAX)
        trip(M300_FAULT_CONFIG);
    gates = args[0];
    hot_min = args[1]; hot_max = args[2];
    bed_min = args[3]; bed_max = args[4];
    configured = 1;
}
DECL_COMMAND(command_m300_config,
             "m300_config gates=%c hot_min=%hu hot_max=%hu bed_min=%hu bed_max=%hu");

void
command_m300_heartbeat(uint32_t *args)
{
    // A late heartbeat may not rescue an already expired session between ticks.
    irqstatus_t flag = irq_save();
    guard_check();
    heartbeat_time = timer_read_time();
    heartbeat_seen = 1;
    irq_restore(flag);
}
DECL_COMMAND(command_m300_heartbeat, "m300_heartbeat");

void
command_m300_arm(uint32_t *args)
{
    irqstatus_t flag = irq_save();
    uint32_t now = timer_read_time();
    guard_check();
    if (args[0] != M300_ARM_MAGIC || !configured || !gates || armed || fault
        || sched_is_shutdown() || !heartbeat_seen || !is_fresh(now, heartbeat_time)
        || adc_seen != ADC_BOTH || !is_fresh(now, hot_time)
        || !is_fresh(now, bed_time) || !raw_in_range())
        trip(M300_FAULT_ARM);
    armed = 1;
    // Apply the last logical native PWM level, including a cached initial OFF.
    raw_write(GPIOE, 1u << 13, fan_requested & 1);
    raw_write(GPIOE, 1u << 14, fan_requested & 2);
    irq_restore(flag);
    send_state();
}
DECL_COMMAND(command_m300_arm, "m300_arm magic=%u");

void
command_m300_disarm(uint32_t *args)
{
    // Latch shutdown and clear native queues. Re-arm requires firmware restart,
    // so a queued pulse from the previous session cannot become live later.
    trip(M300_FAULT_DISARM);
}
DECL_COMMAND(command_m300_disarm, "m300_disarm");

void
command_m300_query(uint32_t *args)
{
    send_state();
}
DECL_COMMAND_FLAGS(command_m300_query, HF_IN_SHUTDOWN, "m300_query");

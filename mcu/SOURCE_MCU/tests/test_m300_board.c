// SPDX-License-Identifier: GPL-3.0-or-later
// Native C register/scheduler doubles, including the transformed upstream
// gpio.c and adc.c. This is not execution on a physical STM32 or a timing test.
#include <assert.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>

#define CONFIG_M300_CLASSIC 1
#define CONFIG_MACH_STM32F103 1
#define CONFIG_MACH_STM32F1 1
#define CONFIG_MACH_STM32F4 0
#define CONFIG_CLOCK_FREQ 72000000
#define CONFIG_FLASH_APPLICATION_ADDRESS 0x08008000
#define CONFIG_FLASH_SIZE 0x10000
#define CONFIG_RAM_SIZE 0x5000
#define CONFIG_STM32_SERIAL_USART1 1
#define CONFIG_STM32F103GD_DISABLE_SWD 0
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define DECL_CONSTANT(...)
#define DECL_CONSTANT_STR(...)
#define DECL_ENUMERATION(...)
#define DECL_ENUMERATION_RANGE(...)
#define DECL_COMMAND(...)
#define DECL_COMMAND_FLAGS(...)
#define DECL_INIT(...)
#define DECL_SHUTDOWN(...)
#define DECL_TASK(...)
#define HF_IN_SHUTDOWN 1

typedef struct { uint32_t CRL, CRH, IDR, ODR, BSRR; } GPIO_TypeDef;
typedef struct { uint32_t APB2ENR; } RCC_TypeDef;
typedef struct { uint32_t SR, CR1, CR2, SQR1, SQR2, SQR3, DR, SMPR1, SMPR2; } ADC_TypeDef;
static GPIO_TypeDef ports[5];
static RCC_TypeDef rcc;
static ADC_TypeDef adc1, adc2;
#define GPIOA (&ports[0])
#define GPIOB (&ports[1])
#define GPIOC (&ports[2])
#define GPIOD (&ports[3])
#define GPIOE (&ports[4])
#define RCC (&rcc)
#define ADC1 (&adc1)
#define ADC2 (&adc2)
#define RCC_APB2ENR_ADC2EN (1u << 10)
#define ADC1_BASE 0x40012400u
#define RCC_APB2ENR_IOPAEN (1u << 2)
#define RCC_APB2ENR_IOPBEN (1u << 3)
#define RCC_APB2ENR_IOPCEN (1u << 4)
#define RCC_APB2ENR_IOPDEN (1u << 5)
#define RCC_APB2ENR_IOPEEN (1u << 6)
#define ADC_CR2_ADON 1u
#define ADC_CR2_RSTCAL (1u << 3)
#define ADC_CR2_CAL (1u << 2)
#define ADC_CR2_EXTSEL_Pos 17
#define ADC_CR2_EXTTRIG (1u << 20)
#define ADC_CR2_TSVREFE (1u << 23)
#define ADC_CR2_SWSTART (1u << 22)
#define ADC_SR_STRT (1u << 4)
#define ADC_SR_EOC (1u << 1)
#define GPIO(p,n) (((p) - 'A') * 16 + (n))
#define GPIO2PORT(p) ((p) / 16)
#define GPIO2BIT(p) (1u << ((p) % 16))
#define GPIO_INPUT 0
#define GPIO_OUTPUT 1
#define GPIO_ANALOG 3
#define GPIO_FUNCTION(f) (2 | ((f) << 4))
struct gpio_out { void *regs; uint32_t bit; };
struct gpio_in { void *regs; uint32_t bit; };
struct gpio_adc { void *adc; uint32_t chan; };
void gpio_out_reset(struct gpio_out, uint32_t);
void gpio_in_reset(struct gpio_in, int32_t);
void gpio_peripheral(uint32_t, uint32_t, int);
void gpio_clock_enable(GPIO_TypeDef *regs);

typedef unsigned irqstatus_t;
static unsigned irq_depth;
static void (*clock_irq_hook)(void);
static irqstatus_t irq_save(void) { return irq_depth++; }
static void irq_restore(irqstatus_t value) {
    irq_depth = value;
    if (!value && clock_irq_hook) {
        void (*fn)(void)=clock_irq_hook; clock_irq_hook=NULL; fn();
    }
}
struct timer { struct timer *next; uint_fast8_t (*func)(struct timer *); uint32_t waketime; };
enum { SF_DONE, SF_RESCHEDULE };
static struct timer *scheduled;
static void sched_add_timer(struct timer *t) { scheduled = t; }
static unsigned shutdown_active;
static uint8_t sched_is_shutdown(void) { return shutdown_active; }
static uint32_t now_ticks;
static uint32_t timer_read_time(void) {
    uint32_t sampled=now_ticks;
    if (!irq_depth && clock_irq_hook) {
        void (*fn)(void)=clock_irq_hook; clock_irq_hook=NULL; fn();
    }
    return sampled;
}
static uint32_t timer_from_us(uint32_t us) { return 72u * us; }
static void udelay(uint32_t us) { (void)us; }
static int is_enabled_pclock(uint32_t base) { (void)base; return 1; }
static void enable_pclock(uint32_t base) { (void)base; }

static unsigned bsrr_count;
static void *first_bsrr_port;
static uint32_t first_bsrr_value;
static void model_bsrr(GPIO_TypeDef *p, uint32_t value)
{
    if (!bsrr_count++) { first_bsrr_port = p; first_bsrr_value = value; }
    p->BSRR = value;
    p->ODR = (p->ODR | (value & 0xffffu)) & ~(value >> 16);
}
#define M300_WRITE_BSRR(regs, value) model_bsrr(regs, value)
static void model_sync(void *regs)
{
    GPIO_TypeDef *p = regs;
    p->ODR = (p->ODR | (p->BSRR & 0xffffu)) & ~(p->BSRR >> 16);
}

static uint32_t snapshot[13];
static unsigned snapshot_count;
static void sendf(const char *format, ...)
{
    unsigned local = !strncmp(format,"m300_local_cooling_state ",24);
    assert(local || !strncmp(format, "m300_state ", 11));
    va_list ap;
    va_start(ap, format);
    for (unsigned i = 0; i < (local ? 11u : ARRAY_SIZE(snapshot)); i++)
        snapshot[i] = va_arg(ap, unsigned);
    va_end(ap);
    snapshot_count++;
}
static jmp_buf rejected;
static unsigned expect_reject, rejection_count;
void m300_board_shutdown(void);
static void __attribute__((noreturn)) mock_shutdown(const char *msg)
{
    (void)msg;
    if (!expect_reject) {
        fprintf(stderr, "Unexpected MCU shutdown: %s\n", msg);
        assert(expect_reject);
    }
    rejection_count++;
    shutdown_active = 1;
    m300_board_shutdown();
    irq_depth = 0;
    longjmp(rejected, 1);
}
#define shutdown(msg) mock_shutdown(msg)
#include "../overlay/src/stm32/m300_board.c"
// The runner generates these from the exact pinned upstream via our patcher.
#include M300_NATIVE_GPIO_FILE
#include M300_NATIVE_ADC_FILE

void gpio_clock_enable(GPIO_TypeDef *regs) { (void)regs; }
void gpio_peripheral(uint32_t pin, uint32_t mode, int pullup)
{
    m300_check_pin_mode(pin, mode);
    GPIO_TypeDef *p = &ports[GPIO2PORT(pin)];
    model_sync(p);
    raw_mode(p, pin % 16, mode == GPIO_OUTPUT ? 1 : mode == GPIO_ANALOG ? 0 : 8);
    if (pullup) model_bsrr(p, pullup > 0 ? GPIO2BIT(pin) : GPIO2BIT(pin) << 16);
}

#define REJECT(code, expected_fault) do { \
    expect_reject = 1; \
    if (!setjmp(rejected)) { code; assert(!"Expected local rejection"); } \
    expect_reject = 0; \
    assert(fault == (expected_fault)); \
    assert(!armed); \
    assert(!(GPIOC->ODR & ((1u << 8) | (1u << 9)))); \
    assert(!(GPIOD->ODR & (1u << 14))); \
    assert((GPIOE->ODR & (3u << 13)) == (3u << 13)); \
} while (0)

static unsigned mode(GPIO_TypeDef *p, unsigned pin)
{
    return ((pin < 8 ? p->CRL : p->CRH) >> (4 * (pin & 7))) & 15;
}

static void restart_model(void)
{
    memset(ports, 0, sizeof(ports));
    memset(&rcc, 0, sizeof(rcc));
    memset(&adc1, 0, sizeof(adc1));
    memset(&adc2, 0, sizeof(adc2));
    configured = armed = fault = gates = heartbeat_seen = adc_seen = 0;
    hot_raw = bed_raw = hot_min = hot_max = bed_min = bed_max = 0;
    hot_time = bed_time = heartbeat_time = 0;
    fan_requested = 3;
    cool_mode=0; cool_reason=COOL_REASON_STARTUP; cool_levels=3;
    cool_hot_on=1; cool_valid=cool_owner=0; cool_raw=0; cool_age=UINT32_MAX;
    local_hot_raw=local_bed_raw=0; local_hot_time=local_bed_time=0;
    local_seen=local_adc_phase=local_adc_bad=cool_native_seen=0; local_phase_time=local_cycle_time=0;
    now_ticks = 1234567890u; // inherited counter before generic timer_init()
    shutdown_active = irq_depth = bsrr_count = 0;
    scheduled = NULL;
    m300_early_init();
    m300_board_init();
    assert(scheduled==NULL);
    now_ticks=0; // generic timer_init() starts the stable timer epoch
    m300_guard_start_task();
    assert(scheduled==&guard_timer && guard_timer.waketime==timer_from_us(GUARD_US));
    uint32_t first=guard_timer.waketime;
    now_ticks=123u;m300_guard_start_task();
    assert(scheduled==&guard_timer && guard_timer.waketime==first);
    now_ticks=0;
}

static void config_model(uint8_t requested_gates)
{
    uint32_t args[] = { requested_gates, 10, 1900, 1800, 3900 };
    command_m300_config(args);
}

static void adc_model(uint16_t hot, uint16_t bed)
{
    m300_adc_observe(ADC1, 9, hot);
    m300_adc_observe(ADC1, 8, bed);
}

static void prepare(uint8_t requested_gates)
{
    restart_model();
    config_model(requested_gates);
    command_m300_heartbeat(NULL);
    adc_model(156, 3000);
}

static void arm_model(void)
{
    uint32_t arg = M300_ARM_MAGIC;
    command_m300_arm(&arg);
    assert(armed && !fault);
}

static void write_pin(struct gpio_out g, uint32_t value)
{
    gpio_out_write(g, value);
    model_sync(g.regs);
}

static void toggle_pin(struct gpio_out g)
{
    gpio_out_toggle_noirq(g);
    model_sync(g.regs);
}

int main(void)
{
    // Reclaim an AF-active bootloader state; EN must be the first safe write.
    restart_model();
    for (unsigned i=0; i<ARRAY_SIZE(ports); i++)
        ports[i].CRL = ports[i].CRH = 0xbbbbbbbb, ports[i].ODR = 0xffff;
    bsrr_count = 0;
    m300_early_init();
    assert(first_bsrr_port == GPIOD && first_bsrr_value == (1u << 30));
    assert(!(GPIOD->ODR & (1u << 14)) && mode(GPIOD, 14) == 2);
    assert(!(GPIOC->ODR & (3u << 8)) && mode(GPIOC, 8) == 2 && mode(GPIOC, 9) == 2);
    assert((GPIOE->ODR & (3u << 13)) == (3u << 13));
    assert(mode(GPIOE, 13) == 2 && mode(GPIOE, 14) == 2);
    assert((GPIOB->ODR & (3u << 10)) == (3u << 10));
    assert((GPIOD->ODR & ((1u << 8) | (7u << 10))) == ((1u << 8) | (7u << 10)));
    assert(!(GPIOA->ODR & (1u << 15)) && !(GPIOC->ODR & (1u << 10)));
    assert(GPIOC->ODR & (1u << 11));
    assert(mode(GPIOE, 15) == 8 && GPIOE->ODR & (1u << 15));
    assert(mode(GPIOD, 5) == 8 && mode(GPIOD, 1) == 8);
    assert(!(GPIOE->ODR & ((1u << 9) | (1u << 10))) && GPIOB->ODR & (1u << 12));

    // Exercise actual transformed upstream reset/write/toggle entry points.
    prepare(3);
    struct gpio_out heater = gpio_out_setup(GPIO('C',8), 1);
    struct gpio_out enable = gpio_out_setup(GPIO('D',14), 1);
    struct gpio_out step = gpio_out_setup(GPIO('B',3), 1);
    assert(!(GPIOC->ODR & (1u<<8)) && !(GPIOD->ODR & (1u<<14)));
    write_pin(heater, 1); toggle_pin(heater);
    gpio_out_toggle(step); model_sync(step.regs);
    write_pin(enable, 1); toggle_pin(enable);
    assert(!(GPIOB->ODR & (1u<<3)) && !(GPIOD->ODR & (1u<<14)));
    struct gpio_out fan0 = gpio_out_setup(GPIO('E',13), 0);
    struct gpio_out fan1 = gpio_out_setup(GPIO('E',14), 1);
    toggle_pin(fan0); assert(fan_requested & 1);
    toggle_pin(fan0); assert(!(fan_requested & 1));
    assert(!(GPIOE->ODR & (1u<<13)) && (GPIOE->ODR & (1u<<14)));
    arm_model();
    assert(!(GPIOE->ODR & (1u<<13)) && (GPIOE->ODR & (1u<<14)));
    write_pin(heater,1); write_pin(enable,1); toggle_pin(step);
    assert(GPIOC->ODR & (1u<<8)); assert(GPIOD->ODR & (1u<<14));
    assert(GPIOB->ODR & (1u<<3));
    toggle_pin(heater); assert(!(GPIOC->ODR & (1u<<8)));
    write_pin(fan1,0); assert(!(GPIOE->ODR & (1u<<14)));
    REJECT(command_m300_disarm(NULL), M300_FAULT_DISARM);
    write_pin(heater,1); toggle_pin(enable); toggle_pin(fan0);
    assert(!(GPIOC->ODR & (1u<<8)) && !(GPIOD->ODR & (1u<<14)));
    assert(!(GPIOE->ODR & (3u<<13))); // valid cold after deliberate disarm
    shutdown_active=0; // plain clear_shutdown must not clear the local latch
    uint32_t magic=M300_ARM_MAGIC;
    REJECT(command_m300_arm(&magic), M300_FAULT_DISARM);

    // Policy 2: cold idle fans follow the native host WITHOUT ARM and with
    // both motion/heating gates disabled. Cached initial OFF must synchronize
    // even if neither native PWM owner emits another GPIO write.
    restart_model();
    fan0 = gpio_out_setup(GPIO('E',13), 0);
    fan1 = gpio_out_setup(GPIO('E',14), 0);
    assert((GPIOE->ODR & (3u<<13)) == (3u<<13));
    config_model(0); command_m300_heartbeat(NULL); adc_model(125, 3000);
    guard_event(&guard_timer);
    assert(!armed && !gates && !fault && !(GPIOE->ODR & (3u<<13)));
    command_m300_query(NULL); assert(snapshot[2]==0 && snapshot[12]==0);
    write_pin(heater,1); write_pin(enable,1); write_pin(step,1);
    assert(!(GPIOC->ODR & (1u<<8)) && !(GPIOD->ODR & (1u<<14)));
    assert(!(GPIOB->ODR & (1u<<3)));
    write_pin(fan0,1); assert(GPIOE->ODR & (1u<<13));
    toggle_pin(fan0); assert(!(GPIOE->ODR & (1u<<13)));
    write_pin(fan1,1); assert(GPIOE->ODR & (1u<<14));
    now_ticks += timer_from_us(FRESH_US) + 1;
    guard_event(&guard_timer);
    assert(!armed && !fault && (GPIOE->ODR & (3u<<13)) == (3u<<13));
    command_m300_query(NULL); assert(snapshot[12]==1);
    command_m300_heartbeat(NULL); adc_model(125, 3000);
    guard_event(&guard_timer);
    assert(!(GPIOE->ODR & (1u<<13)) && (GPIOE->ODR & (1u<<14)));
    adc_model(0, 3000); guard_event(&guard_timer);
    assert((GPIOE->ODR & (3u<<13)) == (3u<<13));
    adc_model(125, 3000); guard_event(&guard_timer);
    assert(!(GPIOE->ODR & (1u<<13)) && (GPIOE->ODR & (1u<<14)));
    REJECT(arm_model(), M300_FAULT_ARM); // zero gates still cannot ARM
    assert(!(GPIOC->ODR & (1u<<8)) && !(GPIOD->ODR & (1u<<14)));

    // Raw range policy cannot be expanded by a validly encoded host command.
    uint32_t bad_config[]={3, 1, M300_HOT_RAW_MAX+1, 1800, 3900};
    restart_model(); REJECT(command_m300_config(bad_config), M300_FAULT_CONFIG);
    bad_config[2]=1900; bad_config[3]=M300_BED_RAW_MIN-1;
    restart_model(); REJECT(command_m300_config(bad_config), M300_FAULT_CONFIG);
    bad_config[3]=1800; bad_config[4]=M300_BED_RAW_MAX+1;
    restart_model(); REJECT(command_m300_config(bad_config), M300_FAULT_CONFIG);
    prepare(3); REJECT(config_model(3), M300_FAULT_CONFIG);
    prepare(0); REJECT(command_m300_arm(&magic), M300_FAULT_ARM);
    prepare(3); uint32_t wrong=0; REJECT(command_m300_arm(&wrong), M300_FAULT_ARM);
    restart_model(); config_model(3); command_m300_heartbeat(NULL);
    m300_adc_observe(&adc2,9,156); m300_adc_observe(ADC1,8,3000);
    assert(adc_seen == ADC_BED);
    REJECT(command_m300_arm(&magic), M300_FAULT_ARM);

    // Finite timeout, single-channel freshness, and no late-heartbeat rescue.
    prepare(3); arm_model(); now_ticks=timer_from_us(1000000);
    REJECT(command_m300_heartbeat(NULL), M300_FAULT_HEARTBEAT);
    prepare(3); arm_model(); now_ticks=timer_from_us(900000);
    command_m300_heartbeat(NULL); m300_adc_observe(ADC1,8,3000);
    now_ticks=timer_from_us(1000000);
    REJECT(m300_adc_observe(ADC1,9,156), M300_FAULT_ADC_STALE);
    prepare(3); arm_model(); REJECT(m300_adc_observe(ADC1,9,0), M300_FAULT_ADC_RANGE);
    prepare(3); arm_model(); REJECT(m300_adc_observe(ADC1,8,4095), M300_FAULT_ADC_RANGE);
    prepare(3); arm_model(); REJECT(m300_adc_observe(ADC1,9,1901), M300_FAULT_ADC_RANGE);

    // CYCCNT wrap and expiry while unarmed cannot revive old temperature data.
    restart_model(); now_ticks=UINT32_MAX-timer_from_us(300000); config_model(3);
    command_m300_heartbeat(NULL); adc_model(156,3000); arm_model();
    now_ticks+=timer_from_us(500000); guard_check(); assert(armed);
    now_ticks+=timer_from_us(500000);
    REJECT(guard_check(), M300_FAULT_HEARTBEAT);
    prepare(3); now_ticks=timer_from_us(1000000); guard_check();
    assert(adc_seen==0 && !heartbeat_seen);

    // PE15 faults in unarmed and armed states; healthy later does not unlatch.
    prepare(3); GPIOE->IDR|=1u<<15;
    REJECT(guard_event(scheduled), M300_FAULT_PLATFORM);
    GPIOE->IDR&=~(1u<<15); shutdown_active=0;
    REJECT(command_m300_arm(&magic), M300_FAULT_PLATFORM);
    prepare(3); arm_model(); GPIOE->IDR|=1u<<15;
    REJECT(guard_event(scheduled), M300_FAULT_PLATFORM);

    // Native queues cannot wait unarmed and then energize after a later arm.
    prepare(3); REJECT(m300_require_motion(), M300_FAULT_REQUEST);
    prepare(3); REJECT(m300_require_output(GPIOC,1u<<8,20), M300_FAULT_REQUEST);
    prepare(M300_GATE_MOTION); arm_model(); m300_require_motion();
    REJECT(m300_require_output(GPIOC,1u<<8,1), M300_FAULT_REQUEST);
    prepare(M300_GATE_HEAT); arm_model(); m300_require_output(GPIOC,1u<<8,20);
    REJECT(m300_require_motion(), M300_FAULT_REQUEST);
    restart_model(); REJECT(m300_check_output_defaults(GPIO('C',8),0,1), M300_FAULT_CONFIG);

    // Real native pin mode changes cannot seize private/ADC/UART/SWD pins.
    prepare(3); REJECT(gpio_out_setup(GPIO('B',10),1), M300_FAULT_PIN);
    prepare(3); REJECT(gpio_out_setup(GPIO('B',1),1), M300_FAULT_PIN);
    prepare(3); REJECT(gpio_in_setup(GPIO('E',15),1), M300_FAULT_PIN);
    prepare(3); REJECT(gpio_in_setup(GPIO('A',10),1), M300_FAULT_PIN);
    prepare(3); REJECT(m300_check_pin_mode(GPIO('C',8),GPIO_FUNCTION(2)), M300_FAULT_PIN);
    prepare(3); REJECT(m300_check_pin_mode(GPIO('A',13),GPIO_INPUT), M300_FAULT_PIN);
    prepare(3); REJECT(m300_check_pin_mode(GPIO('B',14),GPIO_FUNCTION(5)), M300_FAULT_PIN);
    prepare(3); m300_check_pin_mode(GPIO('A',9),GPIO_FUNCTION(7));
    m300_check_pin_mode(GPIO('A',10),GPIO_FUNCTION(7));
    (void)gpio_in_setup(GPIO('C',7),1);

    // Actual patched native ADC path observes only EOC on the matching channel.
    restart_model(); config_model(3); command_m300_heartbeat(NULL);
    struct gpio_adc hot=gpio_adc_setup(GPIO('B',1));
    struct gpio_adc bed=gpio_adc_setup(GPIO('B',0));
    assert(hot.adc==ADC1 && hot.chan==9 && bed.adc==ADC1 && bed.chan==8);
    adc1.SQR3=9; adc1.SR=ADC_SR_STRT; adc1.DR=156;
    gpio_adc_cancel_sample(hot); assert(adc_seen==0);
    adc1.SQR3=8; adc1.SR=ADC_SR_STRT|ADC_SR_EOC;
    (void)gpio_adc_read(hot); assert(adc_seen==0);
    adc1.SQR3=9; adc1.SR=ADC_SR_STRT|ADC_SR_EOC;
    assert(gpio_adc_read(hot)==156 && adc_seen==ADC_HOT);
    adc1.SQR3=8; adc1.SR=ADC_SR_STRT|ADC_SR_EOC; adc1.DR=3000;
    assert(gpio_adc_read(bed)==3000 && adc_seen==ADC_BOTH);
    arm_model();
    command_m300_query(NULL);
    assert(snapshot[1]==1 && snapshot[2]==1 && snapshot[3]==0);
    assert(snapshot[6]==3 && snapshot[7]==156 && snapshot[8]==3000 && snapshot[12]==0);
    shutdown_active=1; m300_board_shutdown(); command_m300_query(NULL);
    assert(snapshot[2]==0 && snapshot[3]==255 && snapshot[12]==1);
    assert(!irq_depth);
    printf("PASS M300 native guard: %u rejection scenarios; early safe/MS, native GPIO reset/write/toggle, fan shadow resync, ADC EOC/cancel, bounded ranges, queue gates, local latch, freshness/wrap, status/shutdown\n", rejection_count);
    return 0;
}

// The pinned native stepper, board DMA driver and simulated peripheral events.
// No ARM execution, peripheral latency or electrical acceptance is modeled.
#include <assert.h>
#include <setjmp.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CONFIG_M300_CLASSIC 1
#define CONFIG_M300_XY_STEP_DMA_LAB 1
#define CONFIG_INLINE_STEPPER_HACK 1
#define CONFIG_CLOCK_FREQ 72000000
#define container_of(p, t, field) ((t *)((char *)(p) - offsetof(t, field)))
#define DIV_ROUND_UP(x, y) (((x) + (y) - 1) / (y))
#define likely(x) (x)
#define unlikely(x) (x)
#define GPIO(port, bit) (((port) - 'A') * 16 + (bit))
#define DECL_INIT(fn)
#define DECL_TASK(fn)
#define DECL_CONSTANT(name, value)
#define DECL_SHUTDOWN(fn)
#define DECL_COMMAND(fn, format)
#define output(...) ((void)0)
#define sendf(...) discard_response(__VA_ARGS__)
#define armcm_enable_irq(fn, num, pri) ((void)(fn))
#define foreach_oid(i, s, fn) for ((i) = 0; (i) < oid_count && ((s) = oids[i]); (i)++)

typedef struct {
    volatile uint32_t CR1, CR2, SMCR, DIER, SR, EGR, CCMR1, CCMR2, CCER;
    volatile uint32_t CNT, PSC, ARR, CCR1, CCR2;
} TIM_TypeDef;
typedef struct { volatile uint32_t CCR, CNDTR, CPAR, CMAR; } DMA_Channel_TypeDef;
typedef struct { volatile uint32_t ISR, IFCR; } DMA_TypeDef;
typedef struct { volatile uint32_t ODR, BSRR; } GPIO_TypeDef;
static TIM_TypeDef timers[2];
static DMA_Channel_TypeDef channels[7];
static DMA_TypeDef dma;
static GPIO_TypeDef port_b, dir_port;
#define TIM2 (&timers[0])
#define TIM3 (&timers[1])
#define DMA1 (&dma)
#define DMA1_Channel2 (&channels[1])
#define DMA1_Channel3 (&channels[2])
#define DMA1_Channel6 (&channels[5])
#define DMA1_Channel7 (&channels[6])
#define GPIOB (&port_b)
#define DMA_ISR_GIF2 (1u << 4)
#define DMA_ISR_TCIF2 (1u << 5)
#define DMA_ISR_HTIF2 (1u << 6)
#define DMA_ISR_TEIF2 (1u << 7)
#define DMA_ISR_GIF3 (1u << 8)
#define DMA_ISR_TCIF3 (1u << 9)
#define DMA_ISR_HTIF3 (1u << 10)
#define DMA_ISR_TEIF3 (1u << 11)
#define DMA_ISR_GIF6 (1u << 20)
#define DMA_ISR_TCIF6 (1u << 21)
#define DMA_ISR_HTIF6 (1u << 22)
#define DMA_ISR_TEIF6 (1u << 23)
#define DMA_ISR_GIF7 (1u << 24)
#define DMA_ISR_TCIF7 (1u << 25)
#define DMA_ISR_HTIF7 (1u << 26)
#define DMA_ISR_TEIF7 (1u << 27)
#define TIM_CR1_CEN 1u
#define TIM_CR1_URS 4u
#define TIM_EGR_UG 1u
#define TIM_SR_UIF 1u
#define TIM_DIER_UDE (1u << 8)
#define TIM_DIER_CC1DE (1u << 9)
#define TIM_DIER_CC2DE (1u << 10)
#define DMA_CCR_EN 1u
#define DMA_CCR_TEIE (1u << 3)
#define DMA_CCR_DIR (1u << 4)
#define DMA_CCR_PSIZE_1 (1u << 9)
#define DMA_CCR_MSIZE_1 (1u << 11)
#define DMA_CCR_PL_0 (1u << 12)
#define DMA_CCR_PL_1 (1u << 13)

enum { SF_DONE, SF_RESCHEDULE };
struct timer { uint32_t waketime; uint_fast8_t (*func)(struct timer *); };
struct trsync_signal { int unused; };
struct trsync { int unused; };
struct task_wake { int pending; };
struct gpio_out { GPIO_TypeDef *regs; uint32_t bit; };
struct move_node { struct move_node *next; };
struct move_queue_head { struct move_node *first; size_t size; };
struct stepper;
static struct stepper *oids[2];
static uint8_t oid_count;
static uint32_t now, cpu_toggles;
static int armed, expect_shutdown;
static jmp_buf stopped;
static const char *fault_message;
typedef unsigned irqstatus_t;

static void discard_response(const char *format, ...) { (void)format; }
static uint32_t timer_read_time(void) { return now++; }
static uint32_t timer_from_us(uint32_t us) { return us * 72; }
static int timer_is_before(uint32_t a, uint32_t b) { return (int32_t)(a - b) < 0; }
static void irq_disable(void) {}
static void irq_enable(void) {}
static irqstatus_t irq_save(void) { return 0; }
static void irq_restore(irqstatus_t flags) { (void)flags; }
static void enable_pclock(uint32_t clock) { (void)clock; }
static void sched_wake_task(struct task_wake *wake) { wake->pending = 1; }
static int sched_check_wake(struct task_wake *wake)
{
    int result = wake->pending;
    wake->pending = 0;
    return result;
}
static void sched_add_timer(struct timer *timer) { assert(!timer_is_before(timer->waketime, now)); }
static void sched_del_timer(struct timer *timer) { (void)timer; }
static _Noreturn void shutdown(const char *message)
{
    fault_message = message;
    assert(expect_shutdown);
    longjmp(stopped, 1);
}
void m300_require_motion(void)
{
    if (!armed)
        shutdown("motion disarmed");
}
void m300_require_motion_gate(void) { m300_require_motion(); }
static void gpio_out_write(struct gpio_out g, uint32_t on)
{
    if (on)
        g.regs->ODR |= g.bit;
    else
        g.regs->ODR &= ~g.bit;
}
static struct gpio_out gpio_out_setup(uint32_t pin, uint32_t on)
{
    struct gpio_out g = { pin / 16 == 1 ? GPIOB : &dir_port, 1u << (pin % 16) };
    gpio_out_write(g, on);
    return g;
}
static void gpio_out_toggle_noirq(struct gpio_out g)
{
    g.regs->ODR ^= g.bit;
    cpu_toggles++;
}
static void *oid_alloc(uint32_t id, void (*fn)(uint32_t *), size_t size)
{
    (void)fn;
    assert(id < 2 && !oids[id]);
    oid_count++;
    return oids[id] = calloc(1, size);
}
static void *oid_lookup(uint8_t id, void (*fn)(uint32_t *))
{
    (void)fn;
    return oids[id];
}
static struct trsync *trsync_oid_lookup(uint32_t id) { (void)id; return NULL; }
static void trsync_add_signal(struct trsync *trsync, struct trsync_signal *signal,
                              void (*stop)(struct trsync_signal *, uint8_t))
{
    (void)trsync; (void)signal; (void)stop;
}
static void move_queue_setup(struct move_queue_head *queue, size_t size) { queue->size = size; }
static int move_queue_empty(struct move_queue_head *queue) { return !queue->first; }
static struct move_node *move_queue_first(struct move_queue_head *queue) { return queue->first; }
static void move_queue_push(struct move_node *node, struct move_queue_head *queue)
{
    struct move_node **at = &queue->first;
    while (*at)
        at = &(*at)->next;
    *at = node;
}
static struct move_node *move_queue_pop(struct move_queue_head *queue)
{
    struct move_node *node = queue->first;
    queue->first = node->next;
    return node;
}
static void move_queue_clear(struct move_queue_head *queue)
{
    while (queue->first)
        free(move_queue_pop(queue));
}
static void *move_alloc(void) { return calloc(1, 64); }
static void move_free(void *node) { free(node); }

#include "m300_xy_step_dma.c"
#include "native_stepper.c"

static void
apply_bsrr(uint32_t value)
{
    GPIOB->ODR = (GPIOB->ODR | (value & 65535)) & ~(value >> 16);
}

static unsigned
transfer(DMA_Channel_TypeDef *channel, uint32_t value)
{
    if (!(channel->CCR & DMA_CCR_EN) || !channel->CNDTR)
        return 0;
    assert(channel->CPAR == (uint32_t)(uintptr_t)&GPIOB->BSRR);
    // No circular mode or memory/peripheral increment.
    assert(!(channel->CCR & ((1u << 5) | (1u << 6) | (1u << 7))));
    apply_bsrr(value);
    channel->CNDTR--;
    return 1;
}

static void
pulse(uint8_t axis, unsigned high_only)
{
    const struct xy_dma_axis *a = &axes[axis - 1];
    assert(a->timer->CR1 & TIM_CR1_CEN);
    assert(a->timer->DIER == (TIM_DIER_UDE | a->compare_request));
    assert(!(GPIOB->ODR & a->high));
    unsigned rose = transfer(a->rise, a->high);
    assert(!!(GPIOB->ODR & a->high) == rose);
    if (!high_only) {
        assert(transfer(a->fall, a->low) == rose);
        assert(!(GPIOB->ODR & a->high));
    }
}

static void
queue(unsigned oid, unsigned period, unsigned count, int add)
{
    command_queue_step((uint32_t[]){oid, period, count, (uint32_t)add});
}

static uint_fast8_t
event(struct stepper *stepper)
{
    now = stepper->time.waketime;
    return stepper_event(&stepper->time);
}

static int32_t
position(struct stepper *stepper)
{
    return stepper_get_position(stepper) - POSITION_BIAS;
}

static void
block(struct stepper *stepper, unsigned period, unsigned count)
{
    assert(event(stepper) == SF_RESCHEDULE);
    const struct xy_dma_axis *a = &axes[stepper->dma_axis - 1];
    assert(a->timer->ARR + 1 == period);
    assert(*a->compare == 144 + M300_XY_DMA_EDGE_MARGIN);
    assert(a->timer->CNT > *a->compare);
    assert(a->rise->CNDTR == count && a->fall->CNDTR == count);
    for (unsigned i = 0; i < count + 2; i++)
        pulse(stepper->dma_axis, 0); // Excess timer events emit zero edges.
    assert(a->rise->CNDTR == 0 && a->fall->CNDTR == 0);
    a->timer->CNT = period - 1; // Exercise the stop/start fallback.
}

static unsigned
captured_block_count(unsigned index, unsigned period_a, unsigned a, unsigned b)
{
    if (index % 2)
        return b;
    return a + (period_a == 433 && index % 8 == 6);
}

static void
captured_handoffs(struct stepper *stepper, unsigned blocks,
                  unsigned period_a, unsigned period_b,
                  unsigned count_a, unsigned count_b)
{
    command_reset_step_clock((uint32_t[]){0, now + 3000});
    for (unsigned i = 0; i < blocks; i++) {
        unsigned count = captured_block_count(i, period_a, count_a, count_b);
        queue(0, i % 2 ? period_b : period_a, count, 0);
    }
    int32_t start_position = position(stepper);
    uint32_t old_toggles = cpu_toggles;
    assert(event(stepper) == SF_RESCHEDULE);
    uint32_t completed = 0;
    const struct xy_dma_axis *a = &axes[0];
    for (unsigned i = 0; i < blocks; i++) {
        uint32_t period = a->timer->ARR + 1;
        uint32_t count = a->rise->CNDTR;
        assert(count == captured_block_count(i, period_a, count_a, count_b));
        assert(period == (i % 2 ? period_b : period_a));
        for (unsigned j = 0; j < count; j++)
            pulse(1, 0);
        completed += count;
        assert(position(stepper) == start_position - (int32_t)completed);

        // SysTick is servicing a final falling edge in the current cycle.
        // Preserve the counter and fixed phase despite callback latency.
        a->timer->CNT = 240 + (i % 3) * 12;
        a->timer->EGR = 0;
        uint32_t last_clock = stepper->next_step_time;
        uint32_t finish_clock = stepper->time.waketime;
        now = finish_clock + 25 + (i % 3) * 12;
        uint_fast8_t result = stepper_event(&stepper->time);
        if (i + 1 == blocks) {
            assert(result == SF_DONE && !(TIM2->CR1 & TIM_CR1_CEN));
        } else {
            uint32_t next_period = i % 2 ? period_a : period_b;
            assert(result == SF_RESCHEDULE && stepper->dma_mode == M300_DMA_RUNNING);
            uint32_t span = next_period * a->rise->CNDTR;
            assert(stepper->next_step_time == last_clock + span);
            assert(stepper->time.waketime == finish_clock + span);
            assert(a->timer->CNT == 240 + (i % 3) * 12 && !a->timer->EGR);
        }
    }
    assert(cpu_toggles == old_toggles);
}

int main(void)
{
    m300_xy_dma_init();
    assert(m300_xy_dma_axis(GPIO('B', 7)) == 0);
    assert(!m300_xy_dma_eligible(751, 144, 28800));
    assert(!m300_xy_dma_eligible(350, 144, 28800));
    assert(!m300_xy_dma_eligible(625, 72, 28800));
    assert(!m300_xy_dma_eligible(625, 144, 31));
    armed = 1;
    command_config_stepper((uint32_t[]){0, GPIO('B', 3), GPIO('D', 9), 0, 144});
    command_config_stepper((uint32_t[]){1, GPIO('B', 4), GPIO('D', 13), 0, 144});
    struct stepper *x = oids[0], *y = oids[1];
    // Exact adjacent blocks from the static OLED 180 mm/s capture, with wrap.
    now = UINT32_MAX - 2000;
    command_reset_step_clock((uint32_t[]){0, now + 3000});
    queue(0, 625, 13820, 0);
    queue(0, 625, 28800, 0);
    uint32_t first = x->next_step_time;
    assert(position(x) == 0);
    block(x, 625, 13820);
    assert(event(x) == SF_RESCHEDULE);
    assert(position(x) == -13820 && x->next_step_time == first + 625 * 13820);
    block(x, 625, 28800);
    assert(event(x) == SF_DONE && position(x) == -42620);
    assert(cpu_toggles == 0);

    // The corresponding first two blocks from the normal OLED capture.
    queue(0, 625, 22285, 0);
    queue(0, 625, 28800, 0);
    block(x, 625, 22285);
    assert(event(x) == SF_RESCHEDULE);
    block(x, 625, 28800);
    assert(event(x) == SF_DONE && position(x) == -93705);
    assert(cpu_toggles == 0);

    // Preserve the exact gap and pulse count across the field captures.
    captured_handoffs(x, 67, 433, 432, 704, 313);
    captured_handoffs(x, 46, 562, 563, 563, 563);
    captured_handoffs(x, 67, 375, 376, 704, 313);
    int32_t start_position = position(x);

    // A late callback may see a good-looking CNT in the next timer cycle.
    // Use DWT to refuse an unsafe rearm even when both counters are empty.
    command_reset_step_clock((uint32_t[]){0, now + 3000});
    queue(0, 433, 32, 0);
    queue(0, 432, 32, 0);
    block(x, 433, 32);
    TIM2->CNT = 240;
    now = x->time.waketime + 433;
    assert(stepper_event(&x->time) == SF_RESCHEDULE);
    assert(x->dma_mode == M300_DMA_PLANNED && !(TIM2->CR1 & TIM_CR1_CEN));
    assert(position(x) == start_position - 32);
    now += 1;
    assert(stepper_event(&x->time) == SF_RESCHEDULE);
    for (unsigned i = 0; i < 32; i++)
        pulse(1, 0);
    assert(event(x) == SF_DONE && position(x) == start_position - 64);
    start_position = position(x);

    // 300 mm/s nominal single-axis timing, then concurrent diagonal blocks.
    command_reset_step_clock((uint32_t[]){0, now + 3000});
    queue(0, 375, 1024, 0);
    block(x, 375, 1024);
    assert(event(x) == SF_DONE && position(x) == start_position - 1024);
    command_reset_step_clock((uint32_t[]){0, now + 3000});
    command_reset_step_clock((uint32_t[]){1, now + 3000});
    queue(0, 530, 128, 0);
    queue(1, 530, 128, 0);
    assert(event(x) == SF_RESCHEDULE && event(y) == SF_RESCHEDULE);
    for (unsigned i = 0; i < 6; i++) {
        pulse(1, 0);
        pulse(2, 0);
    }
    pulse(1, 1);
    uint32_t before_stop = now;
    stepper_stop(&x->stop_signal, 0);
    assert(now - before_stop >= 144);
    assert(position(x) == start_position - 1031 && position(y) == -6);
    assert(!(TIM2->CR1 & TIM_CR1_CEN) && (TIM3->CR1 & TIM_CR1_CEN));
    apply_bsrr(GPIOB->BSRR);
    assert(!transfer(axes[0].rise, axes[0].high));
    stepper_shutdown();
    apply_bsrr(GPIOB->BSRR);
    assert(position(y) == -6 && !(TIM3->CR1 & TIM_CR1_CEN));
    assert(!(GPIOB->ODR & ((1u << 3) | (1u << 4))));
    assert(!transfer(axes[1].rise, axes[1].high));

    command_reset_step_clock((uint32_t[]){0, now + 3000});
    queue(0, 625, 32, 0);
    command_set_next_step_dir((uint32_t[]){0, 1});
    queue(0, 625, 32, 0);
    block(x, 625, 32);
    assert(event(x) == SF_RESCHEDULE && (dir_port.ODR & (1u << 9)));
    block(x, 625, 32);
    assert(event(x) == SF_DONE && position(x) == start_position - 1031);

    // A changing-period block stays on the native software path.
    command_reset_step_clock((uint32_t[]){1, now + 3000});
    queue(1, 625, 34, -1);
    assert(y->dma_mode == M300_DMA_SOFTWARE);
    unsigned edges = cpu_toggles;
    while (event(y) != SF_DONE)
        ;
    assert(cpu_toggles == edges + 68 && position(y) == -40);

    // Reject an incomplete DMA block, transfer error, and disarmed start.
    queue(1, 625, 32, 0);
    assert(event(y) == SF_RESCHEDULE);
    pulse(2, 0);
    expect_shutdown = 1;
    if (!setjmp(stopped)) {
        event(y);
        assert(0);
    }
    assert(strstr(fault_message, "incomplete"));
    assert(!transfer(axes[1].rise, axes[1].high));
    dma.ISR = DMA_ISR_TEIF2;
    if (!setjmp(stopped)) {
        m300_xy_dma_error_irq();
        assert(0);
    }
    assert(strstr(fault_message, "transfer error"));
    dma.ISR = 0;
    armed = 0;
    if (!setjmp(stopped)) {
        m300_xy_dma_start(1, 625, 144, 32, now);
        assert(0);
    }
    assert(strstr(fault_message, "disarmed") && !(TIM2->CR1 & TIM_CR1_CEN));
    puts("PASS M300 XY STEP DMA register model: captured blocks, phase-preserving"
         " handoffs, late fallback, 300 mm/s timings, concurrent axes, wrap,"
         " count, trigger stop, abort and faults");
}

// The pinned native stepper, gated-timer driver and simulated peripheral events.
// No ARM execution, peripheral latency or electrical acceptance is modeled.
#include <assert.h>
#include <setjmp.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CONFIG_M300_CLASSIC 1
#define CONFIG_M300_XY_STEP_TIMER_LAB 1
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
#define foreach_oid(i, s, fn) for ((i) = 0; (i) < oid_count && ((s) = oids[i]); (i)++)

typedef struct {
    volatile uint32_t CR1, CR2, SMCR, DIER, SR, EGR, CCMR1, CCMR2, CCER;
    volatile uint32_t CNT, PSC, ARR, CCR1, CCR2;
} TIM_TypeDef;
typedef struct { volatile uint32_t IDR, ODR, BSRR, CRL; } GPIO_TypeDef;
static TIM_TypeDef timers[4];
static GPIO_TypeDef port_b, dir_port;
#define TIM2 (&timers[0])
#define TIM3 (&timers[1])
#define TIM4 (&timers[2])
#define TIM5 (&timers[3])
#define GPIOB (&port_b)
#define TIM_CR1_CEN 1u
#define TIM_EGR_UG 1u
#define TIM_CCER_CC1E 1u
#define TIM_CCER_CC2E (1u << 4)

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
static uint8_t oid_count, stalled_self_test_axis;
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
void m300_xy_timer_remap(void) {}
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

#include "m300_xy_step_timer.c"
#include "native_stepper.c"

static unsigned
advance_axis(uint8_t axis, uint32_t ticks)
{
    const struct xy_timer_axis *a = &axes[axis - 1];
    TIM_TypeDef *p = a->pulse, *g = a->gate;
    unsigned rising = 0;
    while (ticks && (p->CR1 & TIM_CR1_CEN) && g->CNT < g->CCR1) {
        assert(g->CR1 & TIM_CR1_CEN);
        unsigned attached = ((GPIOB->CRL >> (4 * a->pin)) & 15) == 9;
        assert(p->CCER == (attached ? a->output_enable : 0));
        uint32_t event = p->CNT < p->CCR1 ? p->CCR1 : p->ARR + 1;
        uint32_t wait = event - p->CNT;
        if (ticks < wait) {
            p->CNT += ticks;
            break;
        }
        ticks -= wait;
        if (event == p->CCR1) {
            assert(!!(GPIOB->IDR & pin_mask(a)) == attached);
            GPIOB->IDR &= ~pin_mask(a);
            g->CNT++;
            p->CNT = event;
        } else {
            assert(!(GPIOB->IDR & pin_mask(a)));
            if (attached)
                GPIOB->IDR |= pin_mask(a);
            p->CNT = 0;
            rising++;
        }
    }
    return rising;
}

void
udelay(uint32_t us)
{
    for (unsigned i = 1; i <= 2; i++)
        if (i != stalled_self_test_axis)
            advance_axis(i, us * 72);
    now += us * 72;
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
replay(struct stepper *s, unsigned oid, const unsigned blocks[][2], unsigned n)
{
    command_reset_step_clock((uint32_t[]){oid, now + 3000});
    for (unsigned i = 0; i < n; i++)
        queue(oid, blocks[i][0], blocks[i][1], 0);
    int32_t start_position = position(s);
    uint32_t steps = 0, toggles = cpu_toggles;
    const struct xy_timer_axis *a = &axes[oid];
    assert(event(s) == SF_RESCHEDULE);
    for (unsigned i = 0; i < n; i++) {
        uint32_t period = blocks[i][0], count = blocks[i][1];
        assert(a->pulse->ARR + 1 == period && a->pulse->CCR1 == 176);
        assert(a->gate->CNT == 0 && a->gate->CCR1 == count);
        assert(advance_axis(oid + 1, period * (count + 2)) == count);
        assert(a->gate->CNT == count && a->pulse->CNT == 176);
        assert(!(GPIOB->IDR & pin_mask(a)));
        assert(advance_axis(oid + 1, 10 * period) == 0);
        steps += count;
        assert(position(s) == start_position - (int32_t)steps);
        uint32_t ideal_last = s->next_step_time;
        now = s->time.waketime + (i % 4) * 25;
        assert(stepper_event(&s->time) == (i + 1 < n ? SF_RESCHEDULE : SF_DONE));
        if (i + 1 < n) {
            // A delayed completion callback still leaves the next train
            // anchored to the planned step clock, with bounded launch skew.
            uint32_t duration = blocks[i + 1][0] * blocks[i + 1][1];
            assert(s->next_step_time == ideal_last + duration);
            assert((int32_t)(s->time.waketime - s->next_step_time) <= 224);
        }
    }
    assert(cpu_toggles == toggles && !(a->pulse->CR1 & TIM_CR1_CEN));
    assert(((GPIOB->CRL >> (4 * a->pin)) & 15) == 1);
}

int main(void)
{
    stalled_self_test_axis = 2;
    m300_xy_timer_init();
    assert(verified == 1 && m300_xy_timer_axis(GPIO('B', 3)) == 0);
    assert(!GPIOB->IDR && !GPIOB->CRL);
    stalled_self_test_axis = 0;
    m300_xy_timer_init();
    assert(verified == 3 && !GPIOB->IDR && !GPIOB->CRL);
    assert(TIM2->SMCR == 0x35 && TIM4->SMCR == 0x17);
    assert(TIM3->SMCR == 0x25 && TIM5->SMCR == 0x17);
    assert(TIM2->CR2 == 0x30 && TIM3->CR2 == 0x30);
    assert(TIM4->CR2 == 0x40 && TIM5->CR2 == 0x40);
    assert(m300_xy_timer_axis(GPIO('B', 7)) == 0);
    assert(!m300_xy_timer_eligible(751, 144, 28800));
    assert(!m300_xy_timer_eligible(350, 144, 28800));
    assert(!m300_xy_timer_eligible(625, 72, 28800));
    assert(!m300_xy_timer_eligible(625, 144, 31));

    armed = 1;
    command_config_stepper((uint32_t[]){0, GPIO('B', 3), GPIO('D', 9), 0, 144});
    command_config_stepper((uint32_t[]){1, GPIO('B', 4), GPIO('D', 13), 0, 144});
    struct stepper *x = oids[0], *y = oids[1];
    now = UINT32_MAX - 2000;
    const unsigned ramp[][2] = {{718,292},{709,281},{701,248},{693,298},
        {685,269},{677,317},{669,290},{662,260},{655,307},{648,279},
        {641,327},{634,297},{628,257},{625,22283},{625,15477}};
    replay(x, 0, ramp, sizeof(ramp) / sizeof(ramp[0]));
    unsigned plateau[96][2];
    for (unsigned i = 0; i < 96; i++) {
        plateau[i][0] = i % 2 ? 432 : 433;
        plateau[i][1] = i % 2 ? 313 : 704 + (i % 8 == 6);
    }
    replay(y, 1, plateau, 96);
    const unsigned high_speed[][2] = {{375,65535},{376,313},{375,1024}};
    replay(x, 0, high_speed, sizeof(high_speed) / sizeof(high_speed[0]));

    int32_t x_start = position(x), y_start = position(y);
    command_reset_step_clock((uint32_t[]){0, now + 3000});
    command_reset_step_clock((uint32_t[]){1, now + 3000});
    queue(0, 530, 128, 0);
    queue(1, 530, 128, 0);
    assert(event(x) == SF_RESCHEDULE && event(y) == SF_RESCHEDULE);
    assert(advance_axis(1, 530 - TIM2->CNT + 6 * 530 + 20) == 7);
    assert(advance_axis(2, 530 - TIM3->CNT + 5 * 530 + 200) == 6);
    // Stop a high pulse without losing its rising edge in the position.
    assert(GPIOB->IDR & (1u << 3));
    assert(position(x) == x_start - 7);
    uint32_t before_stop = now;
    stepper_stop(&x->stop_signal, 0);
    assert(now - before_stop >= 144);
    assert(position(x) == x_start - 7);
    assert(!(TIM2->CR1 & TIM_CR1_CEN) && (TIM3->CR1 & TIM_CR1_CEN));
    assert(advance_axis(1, 6000) == 0);
    stepper_shutdown();
    assert(position(y) == y_start - 6 && !(TIM3->CR1 & TIM_CR1_CEN));
    // The register model does not mirror GPIO remux into IDR on detach.
    GPIOB->IDR = 0;

    x_start = position(x);
    command_reset_step_clock((uint32_t[]){0, now + 3000});
    queue(0, 625, 32, 0);
    command_set_next_step_dir((uint32_t[]){0, 1});
    queue(0, 625, 32, 0);
    assert(event(x) == SF_RESCHEDULE);
    assert(advance_axis(1, 33 * 625) == 32);
    assert(event(x) == SF_RESCHEDULE && (dir_port.ODR & (1u << 9)));
    assert(event(x) == SF_RESCHEDULE);
    assert(advance_axis(1, 33 * 625) == 32);
    assert(event(x) == SF_DONE && position(x) == x_start);

    command_reset_step_clock((uint32_t[]){0, now + 3000});
    queue(0, 625, 32, 0);
    queue(0, 625, 34, -1);
    assert(event(x) == SF_RESCHEDULE);
    assert(advance_axis(1, 33 * 625) == 32);
    assert(event(x) == SF_RESCHEDULE && x->timer_mode == M300_TIMER_SOFTWARE);
    assert(((GPIOB->CRL >> 12) & 15) == 1);
    unsigned edges = cpu_toggles;
    while (event(x) != SF_DONE)
        ;
    assert(cpu_toggles == edges + 68 && position(x) == x_start + 66);

    // Refuse to continue after an incomplete train.
    command_reset_step_clock((uint32_t[]){1, now + 3000});
    queue(1, 655, 307, 0);
    queue(1, 648, 279, 0);
    assert(event(y) == SF_RESCHEDULE);
    assert(advance_axis(2, 306 * 655) == 306);
    expect_shutdown = 1;
    if (!setjmp(stopped)) {
        event(y);
        assert(0);
    }
    assert(strstr(fault_message, "incomplete pulse train"));
    m300_xy_timer_abort_all();
    assert(advance_axis(2, 655 * 12) == 0);
    armed = 0;
    if (!setjmp(stopped)) {
        m300_xy_timer_start(1, 625, 144, 32, now);
        assert(0);
    }
    assert(strstr(fault_message, "disarmed") && !(TIM2->CR1 & TIM_CR1_CEN));
    m300_xy_timer_report_task();
    puts("PASS M300 XY gated STEP timer model: captured ramps, alternating"
         " periods, 65535 pulses, hardware gate, stop, direction and fallback");
}

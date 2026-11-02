// Explicit ADC interrupt interleavings. Native register model, NOT hardware.
#define main original_board_tests
#include "test_m300_board.c"
#undef main

static unsigned irq_events;
static void fresh_adc_irq(void)
{
    // Represents a conversion IRQ completing just after a task sampled now.
    // The production ISR updates these fields while its IRQ mask is held.
    now_ticks += timer_from_us(1);
    hot_time=bed_time=now_ticks;
    ++irq_events;
}

static void pending_adc(void)
{
    prepare(3); arm_model();
    now_ticks += timer_from_us(10000);
    irq_events=0;clock_irq_hook=fresh_adc_irq;
}

int main(void)
{
    assert(original_board_tests()==0);
    pending_adc();
#ifdef M300_OLD_SNAPSHOT_API
    expect_reject=1;
    if (!setjmp(rejected)) {
        m300_require_motion();
        assert(!"old code did not reproduce the IRQ race");
    }
    expect_reject=0;
    assert(fault==M300_FAULT_ADC_STALE);
    puts("REPRODUCED_OLD_FALSE_ADC_STALE fault=2 with freshly acquired ADC samples");
    return 77;
#endif
    m300_require_motion();
    assert(armed && !fault && irq_events==1 && !irq_depth);
    puts("PASS_SNAPSHOT motion task / ADC interrupt");

    pending_adc();
    m300_require_output(GPIOC,1u<<8,1);
    assert(armed && !fault && irq_events==1 && !irq_depth);
    puts("PASS_SNAPSHOT heater task / ADC interrupt");

    pending_adc();
    fan_requested=2;
#ifdef M300_OLD_SNAPSHOT_API
    sync_fan_policy(timer_read_time());
#else
    sync_fan_policy();
#endif
    assert(cool_mode==COOL_NATIVE && !fan_forced && irq_events==1 && !irq_depth);
    puts("PASS_SNAPSHOT fan policy / ADC interrupt");

    // Same interleaving straddling the 32-bit timer wrap.
    prepare(3);now_ticks=UINT32_MAX-32;heartbeat_time=hot_time=bed_time=now_ticks;
    arm_model();irq_events=0;clock_irq_hook=fresh_adc_irq;
    m300_require_motion();
    assert(armed && !fault && irq_events==1 && !irq_depth);
    puts("PASS_SNAPSHOT motion interleave across clock wrap");

    prepare(3);arm_model();now_ticks=timer_from_us(900000);
    command_m300_heartbeat(NULL);m300_adc_observe(ADC1,8,3000);
    now_ticks=timer_from_us(1000000);
    REJECT(m300_require_motion(),M300_FAULT_ADC_STALE);
    puts("PASS_SNAPSHOT genuinely stale single ADC still rejected");

    prepare(3);arm_model();now_ticks=timer_from_us(1000000);
    REJECT(command_m300_heartbeat(NULL),M300_FAULT_HEARTBEAT);
    puts("PASS_SNAPSHOT late heartbeat still cannot rescue a session");
    puts("PASS_GUARD_SNAPSHOT cases=6 existing_guard_rejections=31 physical_hardware=false");
    return 0;
}

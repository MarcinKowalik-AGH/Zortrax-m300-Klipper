// Read-only autonomous cooling. ADC2 is private to this monitor; native
// Klipper heater acquisition retains exclusive ownership of ADC1 registers.
// Both ADC blocks share the existing /8 ADC clock, which is never modified.
// GPL-3.0-or-later.
#define COOL_FRESH_US 1000000u
#define COOL_SAMPLE_US 100000u
#define COOL_ADC_TIMEOUT_US 1000000u
#define COOL_ON_RAW 314u     // ceil(50 * 4095 / 654), stock hotend transfer
#define COOL_OFF_RAW 281u    // floor(45 * 4095 / 654), hysteresis
#define COOL_HOT_MIN 32u
enum { COOL_UNKNOWN, COOL_NATIVE, COOL_LOCAL, COOL_EMERGENCY };
enum { COOL_REASON_NATIVE, COOL_REASON_STARTUP, COOL_REASON_THERMOSTAT,
       COOL_REASON_STALE, COOL_REASON_RANGE, COOL_REASON_ADC_TIMEOUT,
       COOL_REASON_LATCHED_FAULT };

static uint8_t cool_mode, cool_reason = COOL_REASON_STARTUP, cool_levels = 3;
static uint8_t cool_hot_on = 1, cool_valid, cool_owner;
static uint16_t cool_raw;
static uint32_t cool_age = UINT32_MAX;
static uint16_t local_hot_raw, local_bed_raw;
static uint32_t local_hot_time, local_bed_time;
static uint8_t local_seen, local_adc_phase, local_adc_bad;
static uint8_t cool_native_seen;
static uint32_t local_phase_time, local_cycle_time;

static uint8_t
cool_fresh(uint32_t now, uint32_t stamp)
{
    return (uint32_t)(now - stamp) < timer_from_us(COOL_FRESH_US);
}

static uint8_t
critical_cooling_fault(void)
{
    // Normal disconnect/disarm/shutdown may cool autonomously without ever
    // clearing the global fault or enabling heater/motor outputs. A diagnosed
    // acquisition/electrical failure keeps protective full cooling latched.
    return fault && fault != M300_FAULT_HEARTBEAT
        && fault != M300_FAULT_DISARM && fault != M300_FAULT_SHUTDOWN;
}

// A current host heartbeat hands acquisition to native ADC1 immediately,
// including its startup phase. ADC2 is only an offline fallback, not a second
// sampler competing with the native heater channels during configuration.
static uint8_t
cooling_host_expected(uint32_t now)
{
    return configured && !fault && !sched_is_shutdown() && heartbeat_seen
        && is_fresh(now, heartbeat_time);
}

static void
cooling_policy(uint32_t now)
{
    uint16_t hot, bed;
    uint8_t fresh;
    // Cooling freshness has its own evictable tags. Do not alter the native
    // ARM observation flags; stale values may never revive after CYCCNT wrap.
    if (!cool_fresh(now, hot_time)) cool_native_seen &= ~ADC_HOT;
    if (!cool_fresh(now, bed_time)) cool_native_seen &= ~ADC_BED;
    if (cool_native_seen == ADC_BOTH && fan_control_allowed(now)) {
        cool_mode = COOL_NATIVE;
        cool_reason = COOL_REASON_NATIVE;
        cool_owner = 1;
        cool_valid = 1;
        cool_raw = hot_raw;
        cool_age = now - hot_time;
        // Preserve a deterministic hysteresis baseline at ownership handoff.
        if (hot_raw >= COOL_ON_RAW) cool_hot_on = 1;
        else if (hot_raw <= COOL_OFF_RAW) cool_hot_on = 0;
        local_seen = 0;
        return;
    }
    if (cooling_host_expected(now)) {
        // Native ADC startup/stale/invalid samples never borrow a local value
        // to authorize host PWM. Keep both fans protective until ADC1 is valid.
        // This short branch also avoids full offline-policy evaluation in the
        // timer/GPIO IRQ-masked path while UART configuration is in progress.
        cool_mode = COOL_UNKNOWN;
        cool_reason = adc_seen ? COOL_REASON_STALE : COOL_REASON_STARTUP;
        cool_owner = 1;
        cool_valid = 0;
        cool_raw = hot_raw;
        cool_age = adc_seen & ADC_HOT ? now - hot_time : UINT32_MAX;
        cool_levels = 3;
        local_seen = 0;
        return;
    }
    if (!cool_fresh(now, local_hot_time)) local_seen &= ~ADC_HOT;
    if (!cool_fresh(now, local_bed_time)) local_seen &= ~ADC_BED;
    // Native analog timers intentionally continue after Klipper shutdown.
    // Their observations remain valid read-only cooling measurements, but
    // never grant a new ARM session. Otherwise use the independent ADC2 pair.
    if (cool_native_seen == ADC_BOTH && cool_fresh(now, hot_time)
        && cool_fresh(now, bed_time)) {
        hot = hot_raw; bed = bed_raw;
        cool_age = now - hot_time;
        cool_owner = 1; fresh = 1;
    } else {
        hot = local_hot_raw; bed = local_bed_raw;
        cool_age = local_seen & ADC_HOT ? now - local_hot_time : UINT32_MAX;
        cool_owner = 2;
        fresh = local_seen == ADC_BOTH && cool_fresh(now, local_hot_time)
            && cool_fresh(now, local_bed_time) && !local_adc_bad;
    }
    cool_raw = hot;
    cool_valid = fresh && hot >= COOL_HOT_MIN && hot <= M300_HOT_RAW_MAX
        && bed >= M300_BED_RAW_MIN && bed <= M300_BED_RAW_MAX
        // A known stricter heater envelope remains authoritative after host
        // loss or generic shutdown. Never widen it during cooling handoff.
        && (!configured || (hot_min < hot_max && bed_min < bed_max
                            && hot >= hot_min && hot <= hot_max
                            && bed >= bed_min && bed <= bed_max));
    if (critical_cooling_fault()) {
        cool_mode = COOL_EMERGENCY; cool_reason = COOL_REASON_LATCHED_FAULT;
        cool_levels = 3; return;
    }
    if (!fresh) {
        cool_mode = COOL_UNKNOWN;
        cool_reason = local_adc_bad ? COOL_REASON_ADC_TIMEOUT
            : local_seen || adc_seen ? COOL_REASON_STALE : COOL_REASON_STARTUP;
        cool_levels = 3; return;
    }
    if (!cool_valid) {
        cool_mode = COOL_EMERGENCY; cool_reason = COOL_REASON_RANGE;
        cool_levels = 3; return;
    }
    if (hot >= COOL_ON_RAW) cool_hot_on = 1;
    else if (hot <= COOL_OFF_RAW) cool_hot_on = 0;
    cool_mode = COOL_LOCAL; cool_reason = COOL_REASON_THERMOSTAT;
    cool_levels = cool_hot_on ? 2 : 0; // model fan OFF; heatsink thermostatic
}

static void sync_fan_policy(void);

static void
local_adc_fail(uint32_t now)
{
    local_adc_bad = 1;
    local_seen = 0;
    local_adc_phase = 0;
    local_phase_time = now;
    ADC2->CR2 = 0;
    ADC2->SR = 0;
}

static void
local_adc_start(unsigned channel, uint32_t now)
{
    ADC2->SR = 0;
    ADC2->SQR3 = channel;
    ADC2->CR2 = ADC_CR2_ADON | (7u << ADC_CR2_EXTSEL_Pos)
        | ADC_CR2_EXTTRIG | ADC_CR2_SWSTART;
    local_phase_time = now;
}

void
m300_local_cooling_task(void)
{
    uint32_t now = timer_read_time();
    // DECL_TASK is woken by the native scheduler's permanent 100 ms periodic
    // timer, including after sched_timer_reset/shutdown. There is no timer or
    // callback that can be silently deleted and strand the local monitor.
    if (cooling_host_expected(now)) {
        local_seen = 0; // paused local measurements must not survive a wrap
        if (local_adc_phase || ADC2->CR2) {
            ADC2->CR2 = 0;
            ADC2->SR = 0;
            local_adc_phase = 0;
            local_phase_time = now;
        }
        sync_fan_policy();
        return;
    }
    if (local_adc_phase >= 1 && local_adc_phase <= 4
        && (uint32_t)(now - local_phase_time) >= timer_from_us(COOL_ADC_TIMEOUT_US)) {
        local_adc_fail(now);
    } else if (local_adc_phase >= 6
               && (uint32_t)(now - local_phase_time) >= timer_from_us(COOL_ADC_TIMEOUT_US)) {
        local_adc_fail(now);
    }
    switch (local_adc_phase) {
    case 0:
        if (local_adc_bad && (uint32_t)(now-local_phase_time) < timer_from_us(COOL_SAMPLE_US))
            break;
        RCC->APB2ENR |= RCC_APB2ENR_ADC2EN | RCC_APB2ENR_IOPBEN;
        (void)RCC->APB2ENR;
        // Fixed analog pins only; native ADC1 uses these same analog modes.
        raw_mode(GPIOB, 0, 0); raw_mode(GPIOB, 1, 0);
        ADC2->CR1 = 0;
        ADC2->SQR1 = 0; ADC2->SQR2 = 0;
        ADC2->SMPR1 = 0;
        // Long sample time tolerates input RC settling and simultaneous ADC1
        // activity after a link fault. ADC1 configuration is never touched.
        ADC2->SMPR2 = (7u << 24) | (7u << 27);
        ADC2->CR2 = ADC_CR2_ADON;
        local_phase_time = now; local_adc_phase = 1;
        break;
    case 1:
        if ((uint32_t)(now-local_phase_time) < timer_from_us(10)) break;
        ADC2->CR2 = ADC_CR2_ADON | ADC_CR2_RSTCAL;
        local_phase_time = now; local_adc_phase = 2;
        break;
    case 2:
        if (ADC2->CR2 & ADC_CR2_RSTCAL) break;
        ADC2->CR2 = ADC_CR2_ADON | ADC_CR2_CAL;
        local_phase_time = now; local_adc_phase = 3;
        break;
    case 3:
        if (ADC2->CR2 & ADC_CR2_CAL) break;
        ADC2->CR2 = ADC_CR2_ADON | (7u << ADC_CR2_EXTSEL_Pos) | ADC_CR2_EXTTRIG;
        local_adc_phase = 5;
        local_cycle_time = now - timer_from_us(COOL_SAMPLE_US);
        // fall through
    case 5:
        if ((uint32_t)(now-local_cycle_time) < timer_from_us(COOL_SAMPLE_US)) break;
        local_adc_start(9, now); local_adc_phase = 6;
        break;
    case 6:
        if (!(ADC2->SR & ADC_SR_EOC)) break;
        if (ADC2->SQR3 != 9) { local_adc_fail(now); break; }
        local_hot_raw = ADC2->DR;
        local_hot_time = local_phase_time; local_seen |= ADC_HOT;
        local_adc_start(8, now); local_adc_phase = 7;
        break;
    case 7:
        if (!(ADC2->SR & ADC_SR_EOC)) break;
        if (ADC2->SQR3 != 8) { local_adc_fail(now); break; }
        local_bed_raw = ADC2->DR;
        local_bed_time = local_phase_time; local_seen |= ADC_BED;
        ADC2->SR = 0;
        local_adc_bad = 0;
        local_cycle_time = now; local_adc_phase = 5;
        break;
    default:
        local_adc_fail(now);
    }
    irqstatus_t flag = irq_save();
    sync_fan_policy();
    irq_restore(flag);
}
DECL_TASK(m300_local_cooling_task);

void
command_m300_local_cooling_query(uint32_t *args)
{
    irqstatus_t flag = irq_save();
    uint32_t now = timer_read_time();
    sync_fan_policy();
    uint8_t mode = cool_mode, reason = cool_reason, valid = cool_valid;
    uint8_t owner = cool_owner;
    uint16_t raw = cool_raw;
    uint32_t age = cool_age, levels = GPIOE->ODR;
    irq_restore(flag);
    sendf("m300_local_cooling_state clock=%u mode=%c reason=%c raw=%hu age=%u"
          " valid=%c hotend_on=%c print_on=%c on_raw=%hu off_raw=%hu owner=%c",
          now, mode, reason, raw, age, valid, !!(levels & (1u<<14)),
          !!(levels & (1u<<13)), COOL_ON_RAW, COOL_OFF_RAW, owner);
}
DECL_COMMAND_FLAGS(command_m300_local_cooling_query, HF_IN_SHUTDOWN,
                   "m300_local_cooling_query");

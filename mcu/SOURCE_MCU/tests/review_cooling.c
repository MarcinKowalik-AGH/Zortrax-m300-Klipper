#define main inherited_board_reference_main
#include M300_REVIEW_BOARD_FIXTURE
#undef main

static unsigned checks;
static void check_outputs(unsigned levels) {
    assert(((GPIOE->ODR >> 13) & 3u) == levels);
    assert(!(GPIOC->ODR & (3u<<8)));
    assert(!(GPIOD->ODR & (1u<<14)));
    assert(!armed);
    assert(!irq_depth);
    checks++;
}
static void local_pair(unsigned hot, unsigned bed) {
    local_hot_raw=hot; local_bed_raw=bed;
    local_hot_time=local_bed_time=now_ticks;
    local_seen=ADC_BOTH; local_adc_bad=0;
}
static void tick(void) {
    now_ticks += timer_from_us(100000);
    m300_local_cooling_task();
}
static void finish_pair(unsigned hot, unsigned bed) {
    if (local_adc_phase==5) tick();
    assert(local_adc_phase==6 && ADC2->SQR3==9);
    ADC2->DR=hot; ADC2->SR=ADC_SR_EOC; tick();
    assert(local_adc_phase==7 && ADC2->SQR3==8);
    ADC2->DR=bed; ADC2->SR=ADC_SR_EOC; tick();
    assert(local_adc_phase==5);
}
static void boot_pair(unsigned hot, unsigned bed) {
    restart_model();
    check_outputs(3);  // Unknown sensors retain safe cooling.
    // Sentinel every ADC1 register: local ADC2 setup/conversions must not write it.
    memset(&adc1,0xa5,sizeof(adc1)); ADC_TypeDef before=adc1;
    tick(); assert(local_adc_phase==1);
    tick(); assert(local_adc_phase==2 && (ADC2->CR2 & ADC_CR2_RSTCAL));
    ADC2->CR2 &= ~ADC_CR2_RSTCAL;
    tick(); assert(local_adc_phase==3 && (ADC2->CR2 & ADC_CR2_CAL));
    ADC2->CR2 &= ~ADC_CR2_CAL;
    tick(); assert(local_adc_phase==6);
    finish_pair(hot,bed);
    assert(!memcmp(&adc1,&before,sizeof(adc1)));
    assert(!adc_seen && !heartbeat_seen && !configured && !armed);
    assert(!hot_time && !bed_time && !hot_raw && !bed_raw);
    checks++;
}

int main(void) {
    // Independent numerical oracle uses the decoded original transfer, rather
    // than copying the firmware's raw threshold constants.
    for(unsigned raw=0;raw<4096;raw++) {
        double temp=(double)raw*3270.0/(4095.0*5.0);
        for(unsigned prior=0;prior<2;prior++) {
            restart_model(); local_pair(raw,3000); cool_hot_on=prior;
            sync_fan_policy();
            unsigned valid=raw>=32 && raw<=M300_HOT_RAW_MAX;
            unsigned expected = !valid ? 3 : (temp>=50.0 ? 2 : temp<=45.0 ? 0 : prior ? 2 : 0);
            check_outputs(expected);
            assert(!adc_seen && !configured && !heartbeat_seen);
        }
    }
    boot_pair(136,3000); check_outputs(0);
    finish_pair(400,3000); check_outputs(2);
    finish_pair(300,3000); check_outputs(2); // 47.9C: retain hot latch.
    finish_pair(281,3000); check_outputs(0);
    finish_pair(0,3000); check_outputs(3);
    boot_pair(700,3000); check_outputs(2);
    // Simulated complete power cycle: no RAM state / host configuration survives.
    boot_pair(136,3000); check_outputs(0);

    // Calibration cannot hang tasks indefinitely; ADC2 timeout never grants ARM.
    restart_model(); tick(); tick();
    assert(local_adc_phase==2);
    for(unsigned i=0;i<12;i++) tick();
    assert(local_adc_bad && !local_seen && !adc_seen);
    check_outputs(3);
    // Previously valid cooling data cannot conceal a stuck conversion or
    // an unexpected channel switch in the dedicated converter.
    boot_pair(136,3000);tick();assert(local_adc_phase==6);
    for(unsigned i=0;i<12;i++)tick();
    assert(local_adc_bad && !local_seen && !adc_seen);check_outputs(3);
    boot_pair(136,3000);tick();assert(local_adc_phase==6);
    ADC2->SQR3=8;ADC2->SR=ADC_SR_EOC;tick();
    assert(local_adc_bad && !local_seen && !adc_seen);check_outputs(3);

    // EOC read time must not rejuvenate a conversion started long ago.
    boot_pair(136,3000);tick();assert(local_adc_phase==6);
    uint32_t conversion_started=now_ticks;
    now_ticks+=timer_from_us(900000);
    ADC2->DR=136;ADC2->SR=ADC_SR_EOC;m300_local_cooling_task();
    assert(local_hot_time==conversion_started && local_adc_phase==7);
    now_ticks+=timer_from_us(200000);
    ADC2->DR=3000;ADC2->SR=ADC_SR_EOC;m300_local_cooling_task();
    assert(!(local_seen & ADC_HOT) && !cool_valid);check_outputs(3);

    // Fault latches remain set. Only communication/disarm/normal shutdown may
    // use valid autonomous thermostat readings; diagnosed electrical faults
    // retain BOTH outputs HIGH even when the independent reading is cold.
    unsigned faults[]={M300_FAULT_HEARTBEAT,M300_FAULT_DISARM,M300_FAULT_SHUTDOWN,
        M300_FAULT_ADC_STALE,M300_FAULT_ADC_RANGE,M300_FAULT_PLATFORM,
        M300_FAULT_CONFIG,M300_FAULT_ARM,M300_FAULT_PIN,M300_FAULT_REQUEST};
    for(unsigned i=0;i<sizeof(faults)/sizeof(faults[0]);i++) {
        restart_model(); local_pair(136,3000); fault=faults[i];
        shutdown_active=1; m300_board_shutdown(); sync_fan_policy();
        unsigned local=faults[i]==M300_FAULT_HEARTBEAT || faults[i]==M300_FAULT_DISARM || faults[i]==M300_FAULT_SHUTDOWN;
        check_outputs(local?0:3); assert(fault==faults[i]);
    }

    // Once a native configuration exists, fallback may not relax its known
    // ADC guard range. Check inclusive boundaries on BOTH converter sources.
    const unsigned samples[][2]={{119,3000},{120,3000},{121,3000},
        {349,3000},{350,3000},{351,3000},
        {136,2499},{136,2500},{136,2501},
        {136,3499},{136,3500},{136,3501}};
    for(unsigned owner=1;owner<=2;owner++) {
        for(unsigned i=0;i<sizeof(samples)/sizeof(samples[0]);i++) {
            restart_model();
            uint32_t limits[]={3,120,350,2500,3500};
            command_m300_config(limits);
            fault=M300_FAULT_SHUTDOWN; shutdown_active=1;
            unsigned hot=samples[i][0], bed=samples[i][1];
            if(owner==1) adc_model(hot,bed); else local_pair(hot,bed);
            cool_hot_on=0; sync_fan_policy();
            unsigned valid=hot>=120 && hot<=350 && bed>=2500 && bed<=3500;
            unsigned expected=!valid?3:hot>=314?2:0;
            check_outputs(expected);
            assert(cool_owner==owner && cool_valid==valid);
            assert(fault==M300_FAULT_SHUTDOWN && !heartbeat_seen);
        }
    }

    // Override is per-pin: native GPIO shutdown/PWM writes cannot force the
    // model fan on while cold/hot autonomous cooling owns the outputs.
    restart_model(); local_pair(136,3000); sync_fan_policy();
    struct gpio_out f0=gpio_out_setup(GPIO('E',13),1);
    struct gpio_out f1=gpio_out_setup(GPIO('E',14),1);
    check_outputs(0); toggle_pin(f0); toggle_pin(f1); check_outputs(0);
    local_pair(400,3000); sync_fan_policy();
    write_pin(f0,1);write_pin(f1,0);check_outputs(2);
    config_model(3);command_m300_heartbeat(NULL);adc_model(156,3000);
    sync_fan_policy();check_outputs(1); // Cached native mask restored.
    assert(!fan_forced && cool_mode==COOL_NATIVE);

    // Paused local data may not revive after an entire 32-bit CYCCNT cycle.
    local_pair(136,3000);m300_local_cooling_task();assert(!local_seen);
    heartbeat_seen=0;adc_seen=0;cool_native_seen=0;
    now_ticks=1;sync_fan_policy();check_outputs(3);
    // Eviction survives another apparent wrap to the old timestamp.
    restart_model();local_pair(136,3000);
    now_ticks=timer_from_us(COOL_FRESH_US)+1;sync_fan_policy();
    assert(!local_seen);now_ticks=1;sync_fan_policy();check_outputs(3);

    printf("PASS independent cooling review: %u assertions/cases; native ADC1 registers unchanged; no local ARM; hysteresis/power-cycle/timeout/fault/shadow/wrap\n",checks);
    return 0;
}

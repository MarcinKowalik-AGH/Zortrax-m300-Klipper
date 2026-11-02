// Register model of the actual R14 cooling code and patched native GPIO/ADC.
// ADC2 hardware completion/calibration are explicit boundaries; not a physical
// temperature or F103 cycle test. GPL-3.0-or-later.
#define main board_guard_main
#include "test_m300_board.c"
#undef main

static unsigned cases;
#define CHECKCASE(name) do { ++cases; printf("PASS_AUTOCOOL %s\n", name); } while (0)

static unsigned levels(void) { return (GPIOE->ODR >> 13) & 3; }
static void outputs_safe(void)
{
    assert(!armed);
    assert(!(GPIOC->ODR & (3u << 8)));
    assert(!(GPIOD->ODR & (1u << 14)));
    assert(!(GPIOB->ODR & ((1u<<3)|(1u<<4)|(1u<<7))));
    assert(!(GPIOA->ODR & 1));
}

static void tick(uint16_t h, uint16_t b, unsigned stall)
{
    ADC_TypeDef native_before = adc1;
    unsigned native_seen = adc_seen;
    now_ticks += timer_from_us(100000);
    if (!stall) {
        adc2.CR2 &= ~(ADC_CR2_RSTCAL | ADC_CR2_CAL);
        if (local_adc_phase == 6 || local_adc_phase == 7) {
            adc2.DR = local_adc_phase == 6 ? h : b;
            adc2.SR = ADC_SR_STRT | ADC_SR_EOC;
        }
    }
    m300_local_cooling_task();
    assert(!memcmp(&adc1, &native_before, sizeof(adc1)));
    assert(adc_seen == native_seen); // local samples cannot become ARM samples
    outputs_safe();
}

static void pump(uint16_t h, uint16_t b, unsigned count)
{
    for (unsigned i=0; i<count; ++i) tick(h,b,0);
}

static void local_boot(uint16_t h)
{
    restart_model();
    adc1.SQR3=0xabcdef; adc1.CR2=0x123456; adc1.DR=0x332211;
    assert(levels()==3);
    pump(h,3000,10);
    assert(cool_mode==COOL_LOCAL && cool_owner==2 && cool_valid);
    assert(adc_seen==0 && !configured && !heartbeat_seen);
}

int main(void)
{
    assert(board_guard_main()==0);
    local_boot(156); assert(levels()==0); CHECKCASE("cold power-cycle without host");
    local_boot(400); assert(levels()==2); CHECKCASE("hot power-cycle without host");
    local_boot(314); assert(levels()==2); CHECKCASE("50C ON threshold ceil raw314");
    pump(300,3000,5); assert(levels()==2); CHECKCASE("hysteresis holds ON in band");
    pump(281,3000,5); assert(levels()==0); CHECKCASE("45C OFF threshold floor raw281");
    pump(300,3000,5); assert(levels()==0); CHECKCASE("hysteresis holds OFF in band");

    struct gpio_out p= gpio_out_setup(GPIO('E',13),1);
    struct gpio_out h= gpio_out_setup(GPIO('E',14),1);
    write_pin(p,1);write_pin(h,1);toggle_pin(p);toggle_pin(h);
    assert(levels()==0); CHECKCASE("native PWM and setup cannot override local cold");
    pump(400,3000,5);write_pin(p,1);write_pin(h,0);toggle_pin(h);
    assert(levels()==2); CHECKCASE("native PWM cannot turn hot heatsink fan off or print on");

    local_boot(156);
    p=gpio_out_setup(GPIO('E',13),0);h=gpio_out_setup(GPIO('E',14),1);
    config_model(3);command_m300_heartbeat(NULL);adc_model(156,3000);
    sync_fan_policy();assert(cool_mode==COOL_NATIVE && levels()==2);
    assert(!fan_forced); CHECKCASE("healthy handoff restores cached native ON without GPIO event");
    write_pin(h,0);sync_fan_policy();assert(levels()==0);
    CHECKCASE("healthy native control follows host with no ARM");

    // Loss of heartbeat while native ADC observations are still fresh.
    now_ticks+=timer_from_us(600000);adc_model(400,3000);
    now_ticks+=timer_from_us(500000);guard_check();sync_fan_policy();
    assert(cool_mode==COOL_LOCAL && cool_owner==1 && levels()==2 && !fault);
    CHECKCASE("host loss uses continuing native ADC read-only");
    adc_model(156,3000);sync_fan_policy();assert(levels()==0);
    CHECKCASE("host disconnected cool below OFF");

    // Real shutdown entry remains latched while local cooling continues.
    shutdown_active=1;m300_board_shutdown();assert(levels()==3);
    pump(400,3000,12);assert(fault==M300_FAULT_SHUTDOWN && levels()==2);
    pump(156,3000,8);assert(fault==M300_FAULT_SHUTDOWN && levels()==0);
    assert(shutdown_active && !armed); CHECKCASE("shutdown timer reset does not strand task thermostat");
    command_m300_local_cooling_query(NULL);
    assert(snapshot[0]==now_ticks && snapshot[1]==COOL_LOCAL && snapshot[5]);
    assert(!snapshot[6] && !snapshot[7] && snapshot[8]==314 && snapshot[9]==281);
    CHECKCASE("shutdown-allowed status reports actual override outputs");

    for (unsigned f=1;f<=9;++f) {
        local_boot(156);fault=f;shutdown_active=1;sync_fan_policy();
        unsigned expected = f==M300_FAULT_HEARTBEAT || f==M300_FAULT_DISARM ? 0 : 3;
        assert(levels()==expected && fault==f);outputs_safe();
    }
    CHECKCASE("critical faults retain full cooling; benign loss never clears fault");

    local_boot(156);pump(0,3000,5);assert(levels()==3 && !cool_valid);
    CHECKCASE("unplugged hot sensor full protective cooling");
    pump(156,4095,5);assert(levels()==3 && !cool_valid);
    CHECKCASE("invalid bed sensor full protective cooling");
    pump(2000,3000,5);assert(levels()==3 && !cool_valid);
    CHECKCASE("hotend over hard raw maximum full protective cooling");
    pump(156,3000,5);assert(levels()==0 && cool_valid);
    CHECKCASE("local sensor recovery does not arm or heat");

    local_boot(156);for(unsigned i=0;i<15;++i)tick(156,3000,1);
    assert(levels()==3 && local_adc_bad); CHECKCASE("conversion timeout is bounded and fail-high");
    pump(156,3000,12);assert(levels()==0 && !local_adc_bad);
    CHECKCASE("bounded recalibration after local ADC timeout");
    restart_model();for(unsigned i=0;i<20;++i)tick(156,3000,1);
    assert(levels()==3 && !cool_valid); CHECKCASE("calibration timeout cannot hang MCU task");

    // Old native/local values are evicted before a timer wrap can revive them.
    prepare(3);sync_fan_policy();assert(cool_native_seen==ADC_BOTH);
    now_ticks=timer_from_us(1000001);sync_fan_policy();
    assert(!cool_native_seen);
    now_ticks=0;sync_fan_policy();assert(levels()==3);
    CHECKCASE("expired native values cannot revive after CYCCNT wrap");
    local_boot(156);config_model(3);command_m300_heartbeat(NULL);adc_model(156,3000);
    m300_local_cooling_task();assert(!local_seen);
    now_ticks+=timer_from_us(1000001);sync_fan_policy();
    now_ticks=local_hot_time;sync_fan_policy();assert(levels()==3);
    CHECKCASE("paused local values cannot revive after native-ownership wrap");

    local_boot(156);adc2.SQR3=12;local_adc_phase=6;adc2.SR=ADC_SR_EOC;
    tick(156,3000,1);assert(levels()==3 && local_adc_bad);
    CHECKCASE("unexpected ADC2 channel does not publish a cooling sample");
    local_boot(156);
    local_seen=0;cool_native_seen=0;local_adc_phase=6;
    local_phase_time=now_ticks;uint32_t conversion_started=now_ticks;
    now_ticks+=timer_from_us(900000);adc2.SQR3=9;adc2.DR=156;adc2.SR=ADC_SR_EOC;
    m300_local_cooling_task();assert(local_hot_time==conversion_started);
    now_ticks+=timer_from_us(200000);adc2.SQR3=8;adc2.DR=3000;adc2.SR=ADC_SR_EOC;
    m300_local_cooling_task();assert(!cool_valid && levels()==3);
    CHECKCASE("delayed conversion result retains acquisition age and expires");

    // Preserve narrower configured limits, including generic shutdown255,
    // for either read-only native ADC1 or independent local ADC2 samples.
    const uint16_t boundary[][2] = {
        {119,3000},{120,3000},{121,3000},
        {349,3000},{350,3000},{351,3000},
        {156,2499},{156,2500},{156,2501},
        {156,3499},{156,3500},{156,3501}
    };
    for (unsigned owner=1; owner<=2; ++owner) {
        for (unsigned i=0; i<sizeof(boundary)/sizeof(boundary[0]); ++i) {
            local_boot(156);
            uint32_t args[]={0,120,350,2500,3500};
            command_m300_config(args);
            shutdown_active=1;fault=M300_FAULT_SHUTDOWN;
            unsigned hot=boundary[i][0],bed=boundary[i][1];
            if(owner==1) adc_model(hot,bed);
            else pump(hot,bed,8);
            sync_fan_policy();
            unsigned valid=hot>=120 && hot<=350 && bed>=2500 && bed<=3500;
            assert(cool_owner==owner && cool_valid==valid);
            assert(cool_mode==(valid ? COOL_LOCAL : COOL_EMERGENCY));
            assert(valid || levels()==3);
            assert(fault==M300_FAULT_SHUTDOWN);outputs_safe();
            CHECKCASE("configured ADC guard boundary retained after shutdown");
        }
    }
    local_boot(156);
    config_model(3);command_m300_heartbeat(NULL);
    ADC_TypeDef native_before=adc1;
    m300_adc_observe(ADC1,8,3000);
    m300_local_cooling_task();
    assert(adc_seen==ADC_BED && !local_seen && !local_adc_phase);
    assert(ADC2->CR2==0 && cool_mode==COOL_UNKNOWN && !cool_valid && levels()==3);
    assert(!memcmp(&adc1,&native_before,sizeof(adc1)));
    for(unsigned i=0;i<3;++i) {
        now_ticks+=timer_from_us(100000);
        m300_local_cooling_task();
        assert(!local_adc_phase && ADC2->CR2==0 && adc_seen==ADC_BED);
    }
    CHECKCASE("host heartbeat powers ADC2 off before both native ADC channels start");
    m300_adc_observe(ADC1,9,156);m300_adc_observe(ADC1,8,3000);
    m300_local_cooling_task();
    assert(cool_mode==COOL_NATIVE && !fan_forced && ADC2->CR2==0);
    now_ticks+=timer_from_us(1100000);guard_check();
    m300_local_cooling_task();
    assert(local_adc_phase==1 && (ADC2->CR2&ADC_CR2_ADON));
    assert(!armed && !heartbeat_seen);
    CHECKCASE("offline ADC2 restarts after actual heartbeat expiration without ARM");
    assert(!irq_depth);
    printf("PASS_AUTOCOOL_TOTAL cases=%u\n",cases);
    return 0;
}

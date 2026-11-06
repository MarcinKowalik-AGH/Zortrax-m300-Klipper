// Native register model. No physical printer fault injection.
#define main original_board_tests
#include "test_m300_board.c"
#undef main

static void check(uint16_t code, uint8_t kind)
{
    struct m300_error_state state;
    m300_error_snapshot(&state);
    assert(state.code == code && state.kind == kind && state.fatal);
    assert(!armed && !((GPIOC->ODR >> 8) & 3u));
}

int main(void)
{
    assert(original_board_tests() == 0);
    prepare(3); arm_model();
    REJECT(m300_adc_observe(ADC1,9,hot_max+1),M300_FAULT_ADC_RANGE);
    check(11,M300_ERROR_SENSOR);
    uint32_t forged[]={3,0,1};command_m300_error_set(forged);
    check(11,M300_ERROR_SENSOR);
    m300_error_shutdown(2);check(11,M300_ERROR_SENSOR);
    assert(error_state.native_id == 2);

    prepare(3);arm_model();
    REJECT(m300_adc_observe(ADC1,9,0),M300_FAULT_ADC_RANGE);
    check(15,M300_ERROR_SENSOR);
    prepare(3);arm_model();
    REJECT(m300_adc_observe(ADC1,8,bed_min-1),M300_FAULT_ADC_RANGE);
    check(12,M300_ERROR_SENSOR);
    prepare(3);arm_model();
    REJECT(m300_adc_observe(ADC1,8,4095),M300_FAULT_ADC_RANGE);
    check(14,M300_ERROR_SENSOR);

    prepare(3);arm_model();now_ticks+=timer_from_us(1100000);
    heartbeat_time=bed_time=now_ticks;
    REJECT(m300_require_motion(),M300_FAULT_ADC_STALE);
    check(15,M300_ERROR_SENSOR);
    prepare(3);arm_model();now_ticks+=timer_from_us(1100000);
    heartbeat_time=hot_time=now_ticks;
    REJECT(m300_require_motion(),M300_FAULT_ADC_STALE);
    check(14,M300_ERROR_SENSOR);
    prepare(3);arm_model();now_ticks+=timer_from_us(1100000);
    heartbeat_time=now_ticks;
    REJECT(m300_require_motion(),M300_FAULT_ADC_STALE);
    check(0,M300_ERROR_SENSOR);
    prepare(3);arm_model();GPIOE->IDR|=1u<<15;
    REJECT(m300_require_motion(),M300_FAULT_PLATFORM);
    check(0,M300_ERROR_PLATFORM);
    prepare(3);arm_model();now_ticks+=timer_from_us(1100000);
    hot_time=bed_time=now_ticks;
    REJECT(m300_require_motion(),M300_FAULT_HEARTBEAT);
    check(0,M300_ERROR_LINK);

    prepare(3);arm_model();unsigned writes=bsrr_count;
    uint32_t notice[]={3,0,0}, clear[]={0,0,0};
    command_m300_error_set(notice);
    assert(error_state.code==3 && !error_state.fatal);
    command_m300_error_set(clear);
    assert(!error_state.code && !error_state.kind && armed && bsrr_count==writes);
    command_m300_error_set(notice);
    m300_error_shutdown(1);
    assert(error_state.fatal && !error_state.code && error_state.kind==M300_ERROR_TIMER);
    command_m300_error_set(clear);
    assert(error_state.fatal && error_state.kind==M300_ERROR_TIMER);
    assert(armed && bsrr_count==writes); // Metadata itself operates no pins.

    prepare(3);writes=bsrr_count;
    m300_error_shutdown(99);uint32_t heating[]={10,0,1};
    command_m300_error_set(heating);
    assert(error_state.fatal && error_state.code==10 && error_state.source==1);
    assert(error_state.native_id==99 && bsrr_count==writes);
    uint32_t invalid[][3]={{999,0,1},{10,99,1},{10,0,2},{0,0,1},{10,256,0}};
    for(unsigned i=0;i<sizeof(invalid)/sizeof(invalid[0]);i++) {
        command_m300_error_set(invalid[i]);assert(error_state.code==10);
    }
    prepare(3);m300_error_adc(ADC1,9);assert(error_state.code==15);
    prepare(3);m300_error_adc(ADC1,8);assert(error_state.code==14);
    prepare(3);m300_error_adc(ADC2,9);assert(!error_state.fatal);
    for(unsigned i=0;i<sizeof(error_codes)/sizeof(error_codes[0]);i++) {
        const struct m300_error_text *text=m300_error_text(error_codes[i].code,0);
        assert(text==&error_codes[i] && text->title[0] && text->hint1[0]);
    }
    assert(sizeof(error_codes)/sizeof(error_codes[0])==21);
    puts("PASS_M300_ERRORS: local ADC/channel, connector ambiguity, first cause, native timing, metadata-only ACK, catalogue=21");
    return 0;
}

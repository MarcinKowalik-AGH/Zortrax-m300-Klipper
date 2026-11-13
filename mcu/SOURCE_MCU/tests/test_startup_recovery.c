// Real local renderer and lease handler with isolated MMIO doubles.
// Does not flash hardware or modify any printer configuration.
#define main panel_regression_main
#include "test_panel.c"
#undef main

static void advance(void) {
    assert(local_timer_active && registered_timer==&local_timer);
    mock_time=local_timer.waketime;
    unsigned before=byte_count;
    assert(local_timer.func(&local_timer)==SF_RESCHEDULE);
    m300_local_oled_task();
    assert(byte_count-before<=32u);
}
static void reach(unsigned target, unsigned no_logo) {
    unsigned n;
    for(n=0;n<2500 && local_state!=target;n++) {
        if(no_logo)assert(!local_startup_splash && local_state!=LOCAL_SPLASH_HOLD);
        advance();
    }
    assert(n<2500 && local_state==target);
}
int main(int argc,char **argv) {
    assert(argc==2);
    SPI2->SR=1u<<1;
    m300_panel_init();m300_local_oled_task();
    reach(LOCAL_SPLASH_HOLD,0);
    assert(local_startup_splash);
    if(!strcmp(argv[1],"lease")) {
        uint32_t take[]={1},release[]={0};
        unsigned old_bytes=byte_count;
        command_m300_oled_host(take);
        assert(local_state==LOCAL_HANDOVER && !local_startup_splash);
        assert(byte_count==old_bytes); // takeover does not wait or render
        local_wake.wake=1;m300_local_oled_task();
        assert(byte_count==old_bytes);
        command_m300_oled_host(release);
        m300_local_oled_task();
        reach(LOCAL_READY,1);
        assert(local_reason==1 && !local_error.code && !local_error.kind);
    } else if(!strcmp(argv[1],"metadata")) {
        uint32_t detail[]={10,0,0};
        uint32_t before=timer_read_time();unsigned old_bytes=byte_count;
        command_m300_error_set(detail);
        assert(byte_count==old_bytes); // metadata is never an SPI write path
        advance();
        assert(!local_startup_splash && local_state==LOCAL_WINDOW);
        assert(timer_read_time()-before<=timer_from_us(101000));
        reach(LOCAL_READY,1);
        assert(local_error.code==10 && !local_error.fatal);
        uint32_t clear[]={0,0,0};command_m300_error_set(clear);
        for(unsigned i=0;i<2000 && local_error.code;i++) {
            advance();assert(!local_startup_splash && local_state!=LOCAL_SPLASH_HOLD);
        }
        reach(LOCAL_READY,1);
        assert(!local_error.code && !local_error.kind);
    } else if(!strcmp(argv[1],"expiry")) {
        uint32_t take[]={1};command_m300_oled_host(take);
        mock_time=oled_host_seen+timer_from_us(1500001);
        assert(oled_host_event(&oled_host_timer)==SF_DONE);
        m300_local_oled_task();reach(LOCAL_READY,1);
        assert(local_reason==2 && local_error.kind==M300_ERROR_LINK);
    } else assert(!"Unknown case");
    puts("PASS bounded startup, immediate takeover, no splash replay");
    return 0;
}

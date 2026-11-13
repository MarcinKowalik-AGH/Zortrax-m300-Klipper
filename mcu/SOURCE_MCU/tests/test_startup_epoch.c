// Production panel module + actual pinned generic timer_init() with MMIO doubles.
// No physical STM32, no clock-cycle or panel power-on timing claim.
#define M300_TIMER_SCALE 72u
#define main panel_regression_main
#include "test_panel.c"
#undef main

static struct {uint32_t DEMCR;} mock_debug;
static struct {uint32_t CTRL,CYCCNT;} mock_dwt;
static struct {uint32_t CTRL;} mock_systick;
#define CoreDebug (&mock_debug)
#define DWT (&mock_dwt)
#define SysTick (&mock_systick)
#define CoreDebug_DEMCR_TRCENA_Msk (1u<<24)
#define DWT_CTRL_CYCCNTENA_Msk 1u
#define SysTick_CTRL_CLKSOURCE_Msk 4u
#define SysTick_CTRL_TICKINT_Msk 2u
#define SysTick_CTRL_ENABLE_Msk 1u
#define SysTick_IRQn (-1)
static void timer_reset(void) {}
static void timer_kick(void) {}
static void NVIC_SetPriority(int irq,unsigned priority) {
    assert(irq==SysTick_IRQn && priority==2);
}
#include M300_GENERIC_TIMER_INIT_FILE

int main(void) {
    const char *value=getenv("M300_INHERITED_CLOCK");
    uint32_t inherited=value?strtoul(value,NULL,0):864000000u;
    const char *host=getenv("M300_HOST_AT_US");
    uint32_t host_at=host?strtoul(host,NULL,0):0xffffffffu;
    const char *stop=getenv("M300_SHUTDOWN_AT_US");
    uint32_t stop_at=stop?strtoul(stop,NULL,0):0xffffffffu;
    const char *baud=getenv("M300_BAUD");
    if(baud)fake_baud=strtoul(baud,NULL,0);
    unsigned early_config=getenv("M300_EARLY_CONFIG")!=NULL;
    mock_time=mock_dwt.CYCCNT=inherited;
    SPI2->SR=1u<<1;
    m300_panel_init();
    // This is the actual generic implementation from the pinned archive.
    timer_init();
    assert(mock_dwt.CYCCNT==0);
    mock_time=mock_dwt.CYCCNT;
    uint32_t config[]={500000},control[]={50,1,1};
    uint32_t configured_spi=0;
    if(early_config){command_m300_oled_config(config);configured_spi=spi_cr1;}
    unsigned host_seen=0,stop_seen=0,first_task=1,ready=0;
    uint32_t ready_at=0,bytes_at_stop=0,bytes_at_host=0;
    uint8_t frame[8192]={0}, splash[8192]={0};
    unsigned splash_seen=0, wait_frames=0, splash_frames=0;
    uint32_t splash_at=0, splash_exit_at=0;
    unsigned task_spi_max=0;
    for(unsigned tick=0;tick<=5400;tick++) {
        uint32_t elapsed=tick*1000u;
        mock_time=timer_from_us(elapsed);
        if(!stop_seen && elapsed>=stop_at) {
            m300_panel_shutdown();stop_seen=1;bytes_at_stop=byte_count;
            assert(!(GPIOE->ODR&(3u<<9)));
            registered_timer=NULL; // native sched_timer_reset precedes callbacks
            assert(byte_count==bytes_at_stop); // no SPI from shutdown handler
        }
        if(!host_seen && !stop_seen && elapsed>=host_at) {
            command_m300_oled_config(config);
            command_m300_oled_control(control);
            host_seen=1;bytes_at_host=byte_count;
        }
        // Initial main-loop tasks run after all DECL_INIT callbacks. Later
        // local progress is driven only when the registered timer is due.
        if(first_task || local_start_pending){m300_local_oled_task();first_task=0;}
        if(early_config && !stop_seen)assert(spi_cr1==configured_spi);
        if(registered_timer==&local_timer && local_timer.func
           && !timer_is_before(mock_time,local_timer.waketime)) {
            unsigned before=byte_count,offset=local_frame_pos;
            unsigned drawing=local_state==LOCAL_FRAME;
            unsigned drawing_splash=local_startup_splash;
            unsigned was_hold=local_state==LOCAL_SPLASH_HOLD;
            (void)local_timer.func(&local_timer);
            m300_local_oled_task();
            unsigned sent=byte_count-before;
            assert(sent<=32u); // Every task remains one bounded SPI chunk.
            if(sent>task_spi_max)task_spi_max=sent;
            if(drawing && local_frame_pos==offset+32u) {
                memcpy((drawing_splash ? splash : frame)+offset,wire+before,32);
                if(local_frame_pos==8192u) {
                    if(drawing_splash)splash_frames++;
                    else wait_frames++;
                }
            }
            if(was_hold && local_state!=LOCAL_SPLASH_HOLD && !splash_exit_at)
                splash_exit_at=elapsed;
        }
        if(local_state==LOCAL_SPLASH_HOLD && !splash_seen) {
            splash_seen=1;splash_at=elapsed;
        }
        if(host_seen || stop_seen)assert(!local_startup_splash);
        if(local_state==LOCAL_READY && !ready){ready=1;ready_at=mock_time/M300_TIMER_SCALE;}
        if(host_seen && !stop_seen)assert(byte_count==bytes_at_host);
    }
    assert(!panel_configured && !snapshot_count);
    if(host_seen){assert(local_state==LOCAL_HANDOVER);assert(ack_count==1);}
    else assert(!ack_count);
    if(stop_seen){
        assert(panel_fault && local_reason==3 && ready && !local_startup_splash);
        assert(local_state==LOCAL_READY || local_state==LOCAL_ICON_WINDOW || local_state==LOCAL_ICON_FRAME);
        assert(byte_count>bytes_at_stop); // bounded task renders fault Waiting
        assert((GPIOE->ODR&(3u<<9))==(3u<<9));
    }
    const char *output=getenv("M300_FRAME_OUTPUT");
    if(output && ready){FILE *f=fopen(output,"wb");assert(f);assert(fwrite(frame,1,8192,f)==8192);assert(!fclose(f));}
    output=getenv("M300_SPLASH_OUTPUT");
    if(output && splash_seen){FILE *f=fopen(output,"wb");assert(f);assert(fwrite(splash,1,8192,f)==8192);assert(!fclose(f));}
    printf("{\"inherited_clock\":%u,\"ready\":%u,\"ready_at_us\":%u,"
           "\"host\":%u,\"shutdown\":%u,\"bytes\":%u,\"baud\":%u,"
           "\"splash_seen\":%u,\"splash_at_us\":%u,\"splash_exit_us\":%u,"
           "\"splash_frames\":%u,\"wait_frames\":%u,\"task_spi_max\":%u}\n",
           inherited,ready,ready_at,host_seen,stop_seen,byte_count,fake_baud,
           splash_seen,splash_at,splash_exit_at,splash_frames,wait_frames,task_spi_max);
    return 0;
}

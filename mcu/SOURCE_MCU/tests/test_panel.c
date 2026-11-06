// SPDX-License-Identifier: GPL-3.0-or-later
// Offline register/scheduler doubles; this does NOT execute on an STM32.
// Build: cc -std=c11 -Wall -Wextra tests/test_panel.c -o /tmp/test_m300_panel
#include <assert.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { uint32_t CRL, CRH, IDR, ODR, BSRR; } GPIO_TypeDef;
typedef struct { uint32_t CR1, CR2, SR, DR; } SPI_TypeDef;
typedef struct { uint32_t APB2ENR, APB1ENR, APB1RSTR, AHBENR; } RCC_TypeDef;
typedef struct { uint32_t ISR, IFCR; } DMA_TypeDef;
typedef struct { uint32_t CCR, CNDTR, CPAR, CMAR; } DMA_Channel_TypeDef;
typedef struct { uint32_t EXTICR[4]; } AFIO_TypeDef;
typedef struct { uint32_t IMR, RTSR, FTSR, PR; } EXTI_TypeDef;
static DMA_TypeDef mock_dma;
static DMA_Channel_TypeDef mock_dma5;
static AFIO_TypeDef mock_afio;
static EXTI_TypeDef mock_exti;
#define DMA1 (&mock_dma)
#define DMA1_Channel5 (&mock_dma5)
#define AFIO (&mock_afio)
#define EXTI (&mock_exti)
static unsigned mock_encoder_irq_priority, mock_dma_irq_priority;
#define armcm_enable_irq(func, num, priority) do { \
    (void)(func); \
    if(strstr(#func,"encoder")) mock_encoder_irq_priority=(priority); \
    else if(strstr(#func,"dma")) mock_dma_irq_priority=(priority); \
} while (0)
#define NVIC_ClearPendingIRQ(...) do {} while (0)
#define __DMB() do {} while (0)
#define __DSB() do {} while (0)
static GPIO_TypeDef mock_b, mock_c, mock_e;
static SPI_TypeDef mock_spi;
static RCC_TypeDef mock_rcc;
#define GPIOB (&mock_b)
#define GPIOC (&mock_c)
#define GPIOE (&mock_e)
#define SPI2 (&mock_spi)
#define RCC (&mock_rcc)
#define M300_PANEL_TEST 1
#define CONFIG_M300_XY_STEP_TIMER 1
#define DECL_CONSTANT_STR(...)
#define DECL_COMMAND_FLAGS(...)
#define DECL_CONSTANT(...)
#define DECL_COMMAND(...)
#define DECL_INIT(...)
#define DECL_SHUTDOWN(...)
#define DECL_TASK(...)
#define get_pclock_frequency(...) 36000000u
typedef unsigned long irqstatus_t;
static irqstatus_t irq_level;
static irqstatus_t irq_save(void) { irqstatus_t old=irq_level;irq_level=1;return old; }
static void irq_restore(irqstatus_t flag) { irq_level=flag; }
struct trsync { unsigned hits; };
static struct trsync release_trigger;
static struct trsync *trsync_oid_lookup(uint8_t oid) {
    assert(oid == 11);
    return &release_trigger;
}
static void trsync_do_trigger(struct trsync *sync, uint8_t reason) {
    assert(reason == 1);
    sync->hits++;
}
struct timer { struct timer *next; uint_fast8_t (*func)(struct timer*); uint32_t waketime; };
struct task_wake { uint8_t wake; };
enum { SF_DONE, SF_RESCHEDULE };
static struct timer *registered_timer;
static void sched_add_timer(struct timer *t) { registered_timer = t; }
static void sched_del_timer(struct timer *t) { if (registered_timer==t) registered_timer=NULL; }
static void sched_wake_task(struct task_wake *w) { w->wake = 1; }
static uint8_t sched_check_wake(struct task_wake *w) { uint8_t v=w->wake; w->wake=0; return v; }
static uint32_t mock_time;
#ifndef M300_TIMER_SCALE
#define M300_TIMER_SCALE 1u
#endif
static uint32_t timer_read_time(void) { uint32_t t=mock_time;mock_time+=M300_TIMER_SCALE;return t; }
static uint32_t timer_from_us(uint32_t us) { return us*M300_TIMER_SCALE; }
static uint8_t timer_is_before(uint32_t a,uint32_t b) { return (int32_t)(a-b)<0; }

static unsigned cs_low, cs_high, ack_count, last_token, snapshot_count;
static unsigned snapshot_v2;
static uint32_t snapshot_position, snapshot_nav_position, snapshot_invalid;
static unsigned byte_count;
static unsigned host_reply_count, host_reply_state, host_reply_local, host_reply_fault, host_reply_reason;
static uint8_t payload[32], wire[20000];
static uint32_t fake_baud=250000;
static uint32_t m300_uart_baud(void) {return fake_baud;}
static void writel(void *addr, uint32_t value) {
    GPIO_TypeDef *ports[] = {GPIOB, GPIOC, GPIOE};
    for (unsigned i=0; i<3; i++) {
        GPIO_TypeDef *p=ports[i];
        if (addr == &p->BSRR) {
            p->BSRR=value; p->ODR=(p->ODR | (value&65535)) & ~(value>>16);
            if (p==GPIOB) { if(value&(1u<<12))cs_high++; if(value&(1u<<28))cs_low++; }
            return;
        }
    }
    assert(!"Unexpected MMIO write");
}
static void writew(void *addr, uint16_t value) {
    assert(addr == &SPI2->DR);
    assert(!irq_level); // interrupts stay available throughout all SPI bytes
    assert(!(GPIOB->ODR & (1u<<12)));
    assert(byte_count < sizeof(wire));
    wire[byte_count++]=value; SPI2->DR=value;
}
static void *command_decode_ptr(uint32_t token) { (void)token; return payload; }
static void sendf(const char *format, ...) {
    va_list a; va_start(a,format);
    if (strstr(format,"m300_oled_ack")) { last_token=va_arg(a,unsigned); ack_count++; }
    else if(strstr(format,"m300_oled_host_state")) {
        host_reply_count++;
        host_reply_state=va_arg(a,unsigned);host_reply_local=va_arg(a,unsigned);
        host_reply_fault=va_arg(a,unsigned);host_reply_reason=va_arg(a,unsigned);
    }
    else if(strstr(format,"m300_panel_state")) {
        snapshot_count++;
        snapshot_v2 = strstr(format,"m300_panel_state_v2") != NULL;
        (void)va_arg(a,unsigned); (void)va_arg(a,unsigned);
        snapshot_position=va_arg(a,unsigned);
        for(unsigned i=0;i<5;i++)(void)va_arg(a,unsigned);
        snapshot_invalid=va_arg(a,unsigned);
        if(snapshot_v2)snapshot_nav_position=va_arg(a,unsigned);
    }
    else assert(!"Unexpected response");
    va_end(a);
}
static jmp_buf failure;
static unsigned expecting_failure, failures;
static void mock_shutdown(const char *message) {
    (void)message;
    assert(expecting_failure);
    failures++;
    longjmp(failure,1);
}
#define shutdown(msg) mock_shutdown(msg)
#define M300_ERRORS_TEST 1
#define _DECL_STATIC_STR(msg) (strstr(msg, "Timer too close") ? 1u : \
    strstr(msg, "Stepper too far in past") ? 2u : 3u)
static uint8_t panel_shutdown_for_test;
static uint8_t sched_is_shutdown(void) { return panel_shutdown_for_test; }
#include "../overlay/src/stm32/m300_errors.c"
#ifndef M300_PANEL_SOURCE
#define M300_PANEL_SOURCE "../overlay/src/stm32/m300_panel.c"
#endif
#include M300_PANEL_SOURCE
#define REJECT(code) do { expecting_failure=1; if(!setjmp(failure)) { code; assert(!"expected rejection"); } expecting_failure=0; } while(0)

static void sample_n(unsigned count) {
    for(unsigned i=0;i<count;i++) {
        assert(registered_timer);
        mock_time=registered_timer->waketime;
        assert(registered_timer->func(registered_timer)==SF_RESCHEDULE);
    }
}
static void set_ab(unsigned value) {
    GPIOE->IDR=(GPIOE->IDR&~(3u<<7)) | (value<<7);
    EXTI->PR=(1u<<7)|(1u<<8);
    m300_encoder_irq();
    sample_n(1);
}
static void set_button(unsigned value,unsigned samples) {
    if(value)GPIOC->IDR &= ~(1u<<5); else GPIOC->IDR |= 1u<<5;
    sample_n(samples);
}
static void reset_encoder(unsigned held) {
    panel_configured=0;
    position=presses=releases=shorts=longs=invalid_transitions=panel_sequence=0;
    changed=long_sent=0; panel_wake.wake=0;
    GPIOE->IDR=3u<<7;
    GPIOC->IDR=held ? 0 : 1u<<5;
    command_m300_panel_config(NULL);
}

static void test_navigation_report_coalescing(void) {
    reset_encoder(0);
    panel_configured = 0;
    uint32_t config[] = {4};
    command_m300_panel_config_v2(config);
    unsigned initial = snapshot_count;
    for (unsigned tick = 0; tick < 1000; tick++) {
        set_ab(tick & 1 ? 3 : 0); // One invalid diagonal transition per ms.
        m300_panel_task();
    }
    assert(snapshot_count == initial + 4);
    assert(snapshot_v2 && snapshot_invalid == 1000 && !snapshot_nav_position);
    assert(!snapshot_position && !nav_partial);

    set_ab(2); // One valid partial edge still waits for the heartbeat.
    sample_n(20);
    m300_panel_task();
    assert(snapshot_count == initial + 4 && position == 1);
    set_ab(0); set_ab(1); set_ab(3);
    m300_panel_task();
    assert(snapshot_count == initial + 5 && snapshot_nav_position == 4);
    assert(snapshot_position == 4 && snapshot_invalid == 1000);

    set_ab(0);
    command_m300_panel_query(NULL);
    assert(snapshot_count == initial + 6 && snapshot_invalid == 1001);
    assert(!panel_wake.wake);
    set_button(1, 5);
    sample_n(20);
    m300_panel_task();
    assert(snapshot_count == initial + 7);

    // During a held jog, the host needs raw edges and invalid reports promptly.
    set_ab(1);
    sample_n(20);
    m300_panel_task();
    assert(snapshot_count == initial + 8 && snapshot_position == 5);
    assert(snapshot_nav_position == 4);
    set_ab(2);
    sample_n(20);
    m300_panel_task();
    assert(snapshot_count == initial + 9 && snapshot_invalid == 1002);
    set_button(0, 5);
    sample_n(20);
    m300_panel_task();
    assert(snapshot_count == initial + 10 && !pressed);

    // Old hosts keep the original raw AB report cadence.
    reset_encoder(0);
    set_ab(0);
    sample_n(20);
    m300_panel_task();
    assert(snapshot_count == initial + 11 && !snapshot_v2 && snapshot_invalid == 1);
}

int main(void) {
    const char *baud_env=getenv("M300_BAUD");
    if(baud_env)fake_baud=strtoul(baud_env,NULL,10);
    m300_panel_init();
    assert(!registered_timer); // no timer before the generic clock reset
    assert(!(GPIOE->ODR&(1u<<9)));
    mock_time=0; // models generic timer_init() after DECL_INIT callbacks
    m300_local_oled_task();
    assert((GPIOB->ODR & (1u<<12)) && !(GPIOB->ODR & (1u<<14)));
    assert((GPIOE->ODR&(1u<<9)) && !(GPIOE->ODR&(1u<<10)));
    assert(((GPIOB->CRH>>24)&15)==2); // PB14 starts GPIO output, never MISO
    assert(((GPIOE->CRL>>28)&15)==8 && (GPIOE->CRH&15)==8);
    assert(((GPIOC->CRL>>20)&15)==8);
    // Progress entirely from the local timer: no host and no panel_config.
    SPI2->SR=1u<<1;
    uint8_t frame[8192];
    for(unsigned i=0;i<1000 && local_state!=LOCAL_READY;i++) {
        mock_time=local_timer.waketime;
        assert(local_timer.func(&local_timer)==SF_RESCHEDULE);
        unsigned before_bytes=byte_count, before_pos=local_frame_pos;
        unsigned was_frame=local_state==LOCAL_FRAME;
        m300_local_oled_task();
        assert(byte_count-before_bytes<=32);
        if(was_frame)memcpy(frame+before_pos,wire+before_bytes,32);
    }
    assert(local_state==LOCAL_READY && local_frame_pos==8192);
    assert(!panel_configured && !oled_configured && !panel_fault);
    assert(GPIOE->ODR&(1u<<10));
    const char *outfile=getenv("M300_FRAME_OUTPUT");
    if(outfile) {FILE *f=fopen(outfile,"wb");assert(f);assert(fwrite(frame,1,8192,f)==8192);assert(!fclose(f));}
    // Local animation changes only its 52 x 50 window, exactly every 500 ms.
    // Decode the actual SPI data back into the original complete screen.
    for(unsigned animation=1;animation<=4;animation++) {
        uint32_t due=local_due;
        mock_time=due-timer_from_us(1000);
        assert(local_timer.func(&local_timer)==SF_RESCHEDULE);
        unsigned saved=byte_count;
        m300_local_oled_task();
        assert(byte_count==saved && local_state==LOCAL_READY);
        assert(local_timer.waketime==due); // no 1 kHz wake while idle
        mock_time=due;
        assert(local_timer.func(&local_timer)==SF_RESCHEDULE);
        m300_local_oled_task();
        assert(local_state==LOCAL_ICON_WINDOW);
        saved=byte_count;
        m300_local_oled_task(); // no timer wake, no work
        assert(byte_count==saved);
        mock_time=local_timer.waketime;
        local_timer.func(&local_timer);m300_local_oled_task();
        const uint8_t window[]={0x15,0x4e,0x5a,0x75,7,56,0x5c};
        assert(byte_count-saved==sizeof(window) && !memcmp(wire+saved,window,sizeof(window)));
        for(unsigned y=0;y<50;y++) {
            saved=byte_count;
            mock_time=local_timer.waketime;
            local_timer.func(&local_timer);m300_local_oled_task();
            assert(byte_count-saved==26);
            memcpy(frame+(y+7)*128+100,wire+saved,26);
        }
        assert(local_state==LOCAL_READY && local_animation_frame==(animation&3u));
        for(unsigned y=0;y<50;y++)for(unsigned x=0;x<52;x++) {
            unsigned actual=(frame[(y+7)*128+100+x/2]>>((x&1u)?0:4))&15u;
            unsigned expected=x<50 && (local_activity_frames[0][animation&3u][y*7+x/8]&(0x80u>>(x&7u)))?15:0;
            assert(actual==expected);
        }
        // Keep the fixed-size test wire buffer bounded across complete cycles.
        byte_count=0;
    }
    byte_count=0;
    uint32_t config[]={1000000}, control[]={1,1,1};
    REJECT(command_m300_oled_control(control));
    command_m300_oled_config(config);
    assert(((GPIOB->CRH>>24)&15)==2);
    assert(local_state==LOCAL_READY && (GPIOE->ODR&(1u<<10)));
    assert(((GPIOB->CRH>>20)&15)==0xb && ((GPIOB->CRH>>28)&15)==0xb);
    assert((SPI2->CR1 & ((1u<<15)|(1u<<14))) == ((1u<<15)|(1u<<14)));
    assert((36000000u >> (((SPI2->CR1>>3)&7)+1)) <= 1000000);
    REJECT(command_m300_oled_config(config));
    command_m300_oled_control(control);
    assert(local_state==LOCAL_HANDOVER);
    assert((GPIOE->ODR&((1u<<9)|(1u<<10)))==((1u<<9)|(1u<<10)));
    assert(ack_count==1 && last_token==1);
    for(unsigned i=0;i<32;i++)payload[i]=i;
    SPI2->SR=1u<<1;
    uint32_t write[]={2,1,32,0}; unsigned before=cs_low;
    command_m300_oled_write(write);
    assert(byte_count==32 && !memcmp(payload,wire,32));
    assert(cs_low-before==1 && (GPIOB->ODR&(1u<<12)));
    assert(GPIOB->ODR&(1u<<14));
    assert(ack_count==2 && last_token==2);
    write[2]=33;REJECT(command_m300_oled_write(write));
    write[2]=0;REJECT(command_m300_oled_write(write));
    write[2]=1;write[1]=2;REJECT(command_m300_oled_write(write));
    write[1]=1;SPI2->SR=0;
    uint32_t time_before=mock_time;
    REJECT(command_m300_oled_write(write));
    assert(mock_time-time_before<=1002); // timeout bound, no unbounded wait
    SPI2->SR=1u<<1;SPI2->CR1^=1;
    REJECT(command_m300_oled_write(write));
    SPI2->CR1=spi_cr1;

    // Decode a literal followed by the longest run at an unaligned offset.
    memcpy(payload, (uint8_t[]){1, 0x12, 0x34, 0xff, 0x55}, 5);
    uint32_t burst[] = {3, 1, 1, 130, 5, 0};
    command_m300_oled_burst(burst);
    struct oled_slot *slot = &oled_slots[oled_head];
    assert(oled_count == 1 && slot->length == 130 && slot->token == 3);
    assert(slot->data[0] == 0x12 && slot->data[1] == 0x34);
    for (unsigned i = 2; i < slot->length; i++)
        assert(slot->data[i] == 0x55);
    burst[3] = 129;
    REJECT(command_m300_oled_burst(burst));
    burst[3] = 130;
    burst[4] = 4;
    REJECT(command_m300_oled_burst(burst));
    assert(oled_count == 1 && ack_count == 2);
    m300_oled_dma_task();
    assert(mock_dma5.CNDTR == 130 && ack_count == 2);
    mock_dma.ISR = 1u << 17;
    m300_oled_dma_irq();
    m300_oled_dma_task();
    assert(!oled_count && ack_count == 3 && last_token == 3);

    reset_encoder(0);
    REJECT(command_m300_panel_config(NULL));
    set_ab(2);set_ab(0);set_ab(1);set_ab(3);assert(position==4);
    set_ab(1);set_ab(0);set_ab(2);set_ab(3);assert(position==0);
    set_ab(2);set_ab(3);assert(position==0); // bounce cancels
    set_ab(0);assert(invalid_transitions==1 && position==0);
    set_ab(3);assert(invalid_transitions==2 && position==0);
    set_button(1,2);set_button(0,2);assert(presses==0); // reject contact bounce
    set_button(1,5);assert(pressed && presses==1);
    set_button(0,5);assert(!pressed && releases==1 && shorts==1 && longs==0);
    set_button(1,5);sample_n(600);assert(longs==1);
    sample_n(700);assert(longs==1); // one long per hold
    set_button(0,5);assert(releases==2 && shorts==1);
    assert(panel_wake.wake);m300_panel_task();assert(snapshot_count==1);
    command_m300_panel_query(NULL);assert(snapshot_count==2);

    test_navigation_report_coalescing();
    reset_encoder(0);
    set_button(1,5);
    uint32_t arm_release[] = {11, presses};
    command_m300_panel_release_arm(arm_release);
    assert(panel_release_sync == &release_trigger && !release_trigger.hits);
    GPIOC->IDR |= 1u << 5;
    EXTI->PR = PANEL_EXTI_RELEASE;
    m300_encoder_irq();
    assert(pressed && release_trigger.hits == 1 && !panel_release_sync);
    set_button(1,1);
    command_m300_panel_release_arm(arm_release);
    assert(release_trigger.hits == 2 && !panel_release_sync);
    set_button(0,5);
    set_button(1,5);
    command_m300_panel_release_arm(arm_release);
    assert(release_trigger.hits == 3 && !panel_release_sync);
    arm_release[1] = presses;
    command_m300_panel_release_arm(arm_release);
    set_button(0,1);
    assert(pressed && release_trigger.hits == 4 && !panel_release_sync);
    set_button(0,5);
    set_button(1,5);
    arm_release[1] = presses;
    command_m300_panel_release_arm(arm_release);
    command_m300_panel_release_disarm(arm_release);
    set_button(0,5);
    assert(release_trigger.hits == 4 && !panel_release_sync);

    reset_encoder(1);sample_n(700);assert(longs==0 && shorts==0);
    set_button(0,5);assert(shorts==0 && releases==0);
    set_button(1,5);set_button(0,5);assert(shorts==1);
    m300_panel_shutdown();m300_panel_shutdown();
    assert(!(GPIOE->ODR&((1u<<9)|(1u<<10))));
    assert(GPIOB->ODR&(1u<<12));
    // Even if a native clear_shutdown resumes command dispatch, the display
    // cannot be powered or written by the old session without a full reset.
    REJECT(command_m300_oled_control(control));
    REJECT(command_m300_oled_write(write));
    assert(!(GPIOE->ODR&((1u<<9)|(1u<<10))));
    // Independent local renderer failure is nonfatal, and never retries itself.
    panel_fault=oled_configured=0; byte_count=0;
    m300_panel_init(); SPI2->SR=0;m300_local_oled_task();
    for(unsigned i=0;i<600 && local_state!=LOCAL_FAILED;i++) {
        mock_time=local_timer.waketime;
        local_timer.func(&local_timer);m300_local_oled_task();
    }
    assert(local_state==LOCAL_FAILED && !panel_fault);
    assert(!(GPIOE->ODR&((1u<<9)|(1u<<10))));
    assert(local_timer.func(&local_timer)==SF_DONE);
    SPI2->SR=1u<<1;
    command_m300_oled_config(config); command_m300_oled_control(control);
    assert(local_state==LOCAL_HANDOVER); // host can recover an optional local failure
    // A host can take over at EVERY local phase; the task never writes again.
    for(unsigned phase=LOCAL_OFF;phase<=LOCAL_ICON_FRAME;phase++) {
        if(phase==LOCAL_FAILED || phase==LOCAL_HANDOVER)continue;
        panel_fault=oled_configured=0;m300_panel_init();
        if(phase!=LOCAL_OFF)m300_local_oled_task();
        local_state=phase;command_m300_oled_config(config);
        assert(local_state==phase);command_m300_oled_control(control);
        unsigned nbytes=byte_count;
        local_wake.wake=1;m300_local_oled_task();assert(byte_count==nbytes);
        assert(local_state==LOCAL_HANDOVER);
        m300_panel_shutdown();local_wake.wake=1;m300_local_oled_task();
        assert(byte_count==nbytes && panel_fault);
    }
    // Local fault detail survives a hard shutdown and can be refined later
    // by a small metadata command. No host framebuffer / normal lease needed.
    memset(&error_state,0,sizeof(error_state));
    panel_fault=oled_configured=0;byte_count=0;
    m300_panel_init();m300_error_shutdown(99);panel_shutdown_for_test=1;
    m300_panel_shutdown();m300_local_oled_task();
    for(unsigned i=0;i<2000 && local_state!=LOCAL_READY;i++) {
        mock_time=local_timer.waketime;
        local_timer.func(&local_timer);m300_local_oled_task();
    }
    assert(local_state==LOCAL_READY && local_error.kind==M300_ERROR_SHUTDOWN);
    unsigned generic_bytes=byte_count;
    uint32_t heat_fault[]={10,0,1};command_m300_error_set(heat_fault);
    assert(byte_count==generic_bytes); // command/IRQ paths never render SPI
    for(unsigned i=0;i<2000 && (local_error.code!=10 || local_state!=LOCAL_READY);i++) {
        mock_time=local_timer.waketime;
        local_timer.func(&local_timer);m300_local_oled_task();
    }
    assert(local_state==LOCAL_READY && local_error.code==10 && local_error.fatal);
    assert(byte_count>generic_bytes+8192u);
    assert(local_error.native_id==99 && !oled_host_owned && panel_fault);
    printf("PASS M300 panel: GPIO ownership, TX-only SPI/CS/ACK/bounds, %u rejections, quadrature/debounce/short/long/startup-held/shutdown; local OEM fault redraw\n",failures);
    return 0;
}

/* SPDX-License-Identifier: GPL-3.0-or-later
 * Inventure RC6 local-screen lifecycle, adapted to M300 pins/init/F103 RAM.
 * Only a 128-byte scanline is kept. No full 8192-byte MCU framebuffer.
 * A private 1ms wake timer progresses even with NO host or encoder config.
 */
#include "m300_oled_stock_glyphs.inc"
#include "m300_oled_activity.inc"
#include "m300_error_icons.inc"
#include "m300_oled_startup_logo.inc"
#define M300_STARTUP_LOGO_HOLD_US 2500000u
/* Host and MCU share the stock 50x50 OLED icon envelope and luminance.
 * Normal Klipper menus (including the three-tone Klipper logo) are rendered
 * on the Orange Pi and transferred unchanged as native 4bpp pixel data.
 * The local renderer below is for waiting/disconnected/error screens. */
#define M300_LOCAL_ICON_WIDTH 50u
#define M300_LOCAL_ICON_HEIGHT 50u
#define M300_LOCAL_ICON_BRIGHT 15u
#define M300_LOCAL_SEPARATOR_LEVEL 5u
enum {
    LOCAL_OFF, LOCAL_WAIT_POWER, LOCAL_WAIT_LOW, LOCAL_WAIT_HIGH,
    LOCAL_INIT_CMDS, LOCAL_WINDOW, LOCAL_FRAME, LOCAL_DISPLAY_ON,
    LOCAL_READY, LOCAL_FAILED, LOCAL_HANDOVER,
    LOCAL_ICON_WINDOW, LOCAL_ICON_FRAME, LOCAL_SPLASH_HOLD
};
static uint8_t local_state, local_render_row, local_start_pending;
static uint8_t local_reason, local_timer_active;
static uint8_t local_startup_splash;
static uint8_t local_animation_frame, local_icon_row;
static uint32_t local_due, local_init_pos, local_frame_pos;
static uint8_t local_row[128];
static struct timer local_timer;
static struct task_wake local_wake;
static struct m300_error_state local_error;
static const uint8_t local_init_bytes[] = {
    0xfd,1,0x12,0xae,0,0xb3,1,0x91,0xca,1,0x3f,0xa2,1,0,0xa1,1,0,
    0xa0,2,0x14,0x11,0xb5,1,0,0xab,1,1,0xb4,2,0xa0,0xfd,
    0xc1,1,0x9f,0xc7,1,0x0f,0xb8,15,
    0x0c,0x18,0x24,0x30,0x3c,0x48,0x54,0x60,0x6c,0x78,0x84,0x90,0x9c,0xa8,0xb4,0x00,0,
    0xb1,1,0xe2,0xd1,2,0xa2,0x20,0xbb,1,0x1f,0xb6,1,8,0xbe,1,7,
    0xa6,0,0xa9,0
};
static int local_has_claim(void) {
    return (local_state >= LOCAL_WAIT_POWER && local_state <= LOCAL_READY)
        || local_state == LOCAL_ICON_WINDOW || local_state == LOCAL_ICON_FRAME
        || local_state == LOCAL_SPLASH_HOLD;
}
static void local_oled_cancel(void) {
    irqstatus_t flag=irq_save();
    if(local_timer_active) {
        sched_del_timer(&local_timer);
        local_timer_active=0;
    }
    irq_restore(flag);
    local_start_pending=0;
    local_startup_splash=0;
    local_state=LOCAL_HANDOVER;
}
static void local_oled_recover(uint8_t reason,uint8_t timer_reset) {
    // Safe even during shutdown: no SPI, timer insertion/deletion or waits.
    if(timer_reset)local_timer_active=0;
    local_startup_splash=0; // Never replay the logo on release, disconnect or fault.
    local_reason=reason;
    local_start_pending=2;
    panel_put(GPIOE,9,0);
    sched_wake_task(&local_wake);
}
static void local_oled_failed(void) {
    local_start_pending=0;
    local_startup_splash=0;
    local_state=LOCAL_FAILED;
    panel_put(GPIOB,12,1);
    panel_put(GPIOE,9,0);
    panel_put(GPIOE,10,0);
}
static int local_write(uint8_t dc,const uint8_t *data,unsigned count) {
    if (!local_has_claim() || !panel_spi_burst(dc,data,count)) {
        local_oled_failed(); return 0;
    }
    return 1;
}
static int local_cmd(uint8_t cmd,const uint8_t *data,unsigned count) {
    return local_write(0,&cmd,1) && (!count || local_write(1,data,count));
}
static void local_pixel(unsigned x,int y,unsigned level) {
    if(x>=256u || y!=(int)local_render_row)return;
    unsigned offset=(x>>1), shift=(x&1u)?0u:4u;
    local_row[offset]=(uint8_t)((local_row[offset]&~(15u<<shift))
                                    | ((level&15u)<<shift));
}
static const uint8_t *local_glyph(unsigned code,unsigned *width,unsigned *span) {
    unsigned n=(code>=32u && code<=126u) ? code-32u : '?' - 32u;
    const uint8_t *p=glyph_packed;
    for(unsigned count=0;count<95u;count++) {
        uint8_t header=*p++;
        unsigned w=header>>4u,s=header&15u;
        s=s==15u?*p++:glyph_span[s];
        if(n==0u) {
            *width=w;*span=s;return p;
        }
        p+=(w*(s&15u)+7u)>>3u;
        n--;
    }
    *width=0;*span=0;return glyph_packed;
}
static void local_text(unsigned x,unsigned y,const char *str) {
    while (*str && x<250u) {
        unsigned width,span,code=(uint8_t)*str++;
        const uint8_t *bits=local_glyph(code,&width,&span);
        if(x+width>252u)break;
        int r=(int)local_render_row-((int)y+(int)(span>>4u)-3);
        // Only this scanline can be visible. Do not redraw all glyph rows
        // 64 times just to reject them in local_pixel().
        if(r>=0 && (unsigned)r<(span&15u))
            for(unsigned c=0;c<width;c++) {
                unsigned b=(unsigned)r*width+c;
                if (bits[b>>3u] & (1u<<(b&7u)))
                    local_pixel(x+c,(int)local_render_row,15u);
            }
        x+=width+1u;
    }
}

static void local_render_icon(unsigned row) {
    if(row<7u || row>=7u+M300_LOCAL_ICON_HEIGHT)return;
    unsigned y=row-7u;
    const struct m300_error_text *error=m300_error_text(local_error.code,local_error.kind);
    const uint8_t *pixels=(local_error.code || local_error.kind)
        ? local_error_rle+local_error_frames[error->icon][local_animation_frame][y]
        : local_activity_rle+local_activity_frames[local_reason>=2u][local_animation_frame][y];
    // Immutable, CI-verified row stream. Every token emits 1..16 pixels;
    // at most 50 reads/writes per row, no allocation or full framebuffer.
    unsigned x=0;
    while(x<M300_LOCAL_ICON_WIDTH) {
        unsigned token=*pixels++,end=x+(token>>4u)+1u,level=token&15u;
        if(end>M300_LOCAL_ICON_WIDTH)end=M300_LOCAL_ICON_WIDTH;
        while(x<end) {
            if(level)local_pixel(200u+x,(int)row,level);
            x++;
        }
    }
}
static void local_render(unsigned row) {
    local_render_row=row;
    memset(local_row,0,sizeof(local_row));
    if(local_startup_splash && !local_error.code && !local_error.kind) {
        // OEM bitmap centered at its native size: no scaling or new font.
        if(row>=12u && row<52u)
            memcpy(local_row+24u,m300_startup_logo[row-12u],80u);
        return;
    }
    if(local_error.code || local_error.kind) {
        const struct m300_error_text *error=m300_error_text(local_error.code,local_error.kind);
        char title[]="Error #000";
        title[7]='0'+local_error.code/100;
        title[8]='0'+(local_error.code/10)%10;
        title[9]='0'+local_error.code%10;
        local_text(4,2,local_error.code ? title : "ZORTRAX M300 - Error");
        for(unsigned x=4;x<192;x++)local_pixel(x,12,M300_LOCAL_SEPARATOR_LEVEL);
        local_text(4,18,error->title);
        local_text(4,34,error->hint1);
        local_text(4,50,error->hint2);
        local_render_icon(row);
        return;
    }
    local_text(4,2,"ZORTRAX M300");
    for(unsigned x=4;x<192;x++)local_pixel(x,12,M300_LOCAL_SEPARATOR_LEVEL);
    local_text(4,18,local_reason==3 ? "MCU shutdown" :
               local_reason==2 ? "Klipper disconnected" : "Waiting for Klipper...");
    local_text(4,34,M300_LOCAL_RELEASE_TEXT);
    char line[24]="UART: ",digits[10];
    unsigned n=6,k=0; uint32_t baud=m300_uart_baud();
    do { digits[k++]='0'+baud%10; baud/=10; } while(baud);
    while(k)line[n++]=digits[--k];
    const char suffix[]=" 8N1";
    memcpy(line+n,suffix,sizeof(suffix));
    local_text(4,50,line);
    local_render_icon(row);
}
static uint_fast8_t local_event(struct timer *timer) {
    if (!local_has_claim()) {local_timer_active=0;return SF_DONE;}
    sched_wake_task(&local_wake);
    uint32_t now=timer_read_time();
    // Sleep between frames. No 1 kHz idle wake and no animation over UART.
    if(local_state==LOCAL_SPLASH_HOLD && timer_is_before(now,local_due)) {
        // At most 10 wakeups/s while showing the static logo. Error metadata
        // can preempt it; UART commands/host ownership never wait for this.
        uint32_t poll=now+timer_from_us(100000);
        timer->waketime=timer_is_before(poll,local_due) ? poll : local_due;
    } else {
        timer->waketime=local_state==LOCAL_READY && timer_is_before(now,local_due)
            ? local_due : m300_next_timer(timer->waketime,now,timer_from_us(1000));
    }
    return SF_RESCHEDULE;
}
static void local_oled_init(void) {
    // DECL_INIT(m300_panel_init) precedes generic timer_init(), which resets
    // DWT->CYCCNT. No deadline or scheduler timer may be based on that epoch.
    local_state=LOCAL_OFF;
    local_startup_splash=1; // Only true for a new application startup.
    local_reason=local_timer_active=0;
    local_start_pending=1;
    sched_wake_task(&local_wake);
}
static void local_oled_start(void) {
    local_start_pending=0;
    if(local_state!=LOCAL_OFF)return;
    local_animation_frame=local_icon_row=0;
    (void)m300_uart_baud();
    // A host config received before the first task keeps its selected rate.
    if(!oled_configured || panel_fault)panel_spi_setup(2000000);
    panel_put(GPIOE,9,1);
    local_state=LOCAL_WAIT_POWER;
    local_due=timer_read_time()+timer_from_us(500000);
    local_timer.func=local_event;
    local_timer.waketime=timer_read_time()+timer_from_us(1000);
    local_timer_active=1;
    sched_add_timer(&local_timer);
}
void m300_local_oled_task(void) {
    // Tasks run only after ALL init functions, including timer_init().
    if(local_start_pending==2) {
        // Normal release/expiry cancels live timers here; shutdown already
        // reset the scheduler and cleared these active flags in its callback.
        irqstatus_t flag=irq_save();
        if(local_timer_active)sched_del_timer(&local_timer);
        local_timer_active=0;
        irq_restore(flag);
        oled_dma_cancel_alarm();
        oled_dma_shutdown();
        panel_spi_setup(panel_fault ? 2000000 : (panel_spi_hz ? panel_spi_hz : 2000000));
        local_state=LOCAL_OFF;
    }
    if(local_start_pending)local_oled_start();
    if (!sched_check_wake(&local_wake) || !local_has_claim()) return;
    uint32_t now=timer_read_time();
    if(local_state==LOCAL_WAIT_POWER && !timer_is_before(now,local_due)) {
        local_due=now+timer_from_us(10000); local_state=LOCAL_WAIT_LOW;
    } else if(local_state==LOCAL_WAIT_LOW && !timer_is_before(now,local_due)) {
        panel_put(GPIOE,10,1);
        local_due=now+timer_from_us(20000); local_state=LOCAL_WAIT_HIGH;
    } else if(local_state==LOCAL_WAIT_HIGH && !timer_is_before(now,local_due)) {
        local_init_pos=0;local_state=LOCAL_INIT_CMDS;
    } else if(local_state==LOCAL_INIT_CMDS) {
        if(local_init_pos>=sizeof(local_init_bytes)) {local_state=LOCAL_WINDOW;return;}
        unsigned pos=local_init_pos;
        uint8_t cmd=local_init_bytes[pos++],count=local_init_bytes[pos++];
        if(pos+count>sizeof(local_init_bytes) || !local_cmd(cmd,local_init_bytes+pos,count)) {
            local_oled_failed();return;
        }
        local_init_pos=pos+count;
    } else if(local_state==LOCAL_WINDOW) {
        m300_error_snapshot(&local_error);
        // A connection lease expiry needs no host round trip for diagnosis.
        if(!local_error.fatal && local_reason>=2u) {
            local_error.code=0;
            local_error.kind=local_reason==2u ? M300_ERROR_LINK : M300_ERROR_SHUTDOWN;
        }
        if(local_error.code || local_error.kind || local_reason>=1u)
            local_startup_splash=0;
        const uint8_t col[]={0x1c,0x5b},row[]={0,63};
        if(!local_cmd(0x15,col,2) || !local_cmd(0x75,row,2) || !local_cmd(0x5c,0,0)) return;
        local_frame_pos=0;local_state=LOCAL_FRAME;
    } else if(local_state==LOCAL_FRAME) {
        unsigned x=local_frame_pos%128;
        if(!x)local_render(local_frame_pos/128);
        if(!local_write(1,local_row+x,32))return;
        local_frame_pos+=32;
        if(local_frame_pos==8192)local_state=LOCAL_DISPLAY_ON;
    } else if(local_state==LOCAL_DISPLAY_ON) {
        if(local_cmd(0xaf,0,0)) {
            local_due=now+timer_from_us(local_startup_splash
                ? M300_STARTUP_LOGO_HOLD_US : 500000u);
            local_state=local_startup_splash ? LOCAL_SPLASH_HOLD : LOCAL_READY;
        }
    } else if(local_state==LOCAL_SPLASH_HOLD) {
        struct m300_error_state current;
        m300_error_snapshot(&current);
        if(!timer_is_before(now,local_due) || current.code || current.kind) {
            local_startup_splash=0;
            local_animation_frame=0;
            local_state=LOCAL_WINDOW; // Redraw the whole waiting/error screen.
        }
    } else if(local_state==LOCAL_READY && !timer_is_before(now,local_due)) {
        struct m300_error_state current;
        m300_error_snapshot(&current);
        local_animation_frame=(local_animation_frame+1u)&3u;
        local_due=now+timer_from_us(500000);
        // Late, metadata-only host detail refreshes the local error text.
        // SPI work remains in bounded task context, outside shutdown/IRQs.
        local_state=current.revision!=local_error.revision ? LOCAL_WINDOW : LOCAL_ICON_WINDOW;
    } else if(local_state==LOCAL_ICON_WINDOW) {
        // SSD1322 columns address four pixels. 52 x 50 window; last two
        // pixels stay black. Preserve all text and transfer one row per task.
        const uint8_t col[]={0x4e,0x5a},row[]={7,56};
        if(!local_cmd(0x15,col,2) || !local_cmd(0x75,row,2) || !local_cmd(0x5c,0,0))return;
        local_icon_row=0;
        local_state=LOCAL_ICON_FRAME;
    } else if(local_state==LOCAL_ICON_FRAME) {
        local_render_row=7u+local_icon_row;
        memset(local_row,0,sizeof(local_row));
        local_render_icon(local_render_row);
        if(!local_write(1,local_row+100,26))return;
        if(++local_icon_row==50u)local_state=LOCAL_READY;
    }
}
#line 2000 "m300_oled_local.inc"
DECL_TASK(m300_local_oled_task);
void command_m300_local_oled_query(uint32_t *args) {
    (void)args;
    sendf("m300_local_oled_state state=%c baud=%u",local_state,m300_uart_baud());
}
DECL_COMMAND_FLAGS(command_m300_local_oled_query,HF_IN_SHUTDOWN,"m300_local_oled_query");

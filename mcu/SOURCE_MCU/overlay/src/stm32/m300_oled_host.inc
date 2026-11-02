// SPDX-License-Identifier: GPL-3.0-or-later
// Private display lease only. Never clears shutdown or changes actuator gates.
static uint8_t oled_host_protocol, oled_host_owned, oled_host_timer_active;
static uint32_t oled_host_seen;
static struct timer oled_host_timer;

static uint8_t oled_host_allowed(void) {
    // Older hosts remain wire-compatible, but only the R9 supervisor enables
    // the lease. A released R9 lease never accepts stale background writes.
    return !oled_host_protocol || oled_host_owned;
}
static uint_fast8_t oled_host_event(struct timer *timer) {
    uint32_t now=timer_read_time();
    if(!oled_host_owned || panel_fault) {oled_host_timer_active=0;return SF_DONE;}
    if((uint32_t)(now-oled_host_seen)>=timer_from_us(1500000)) {
        oled_host_owned=0;
        oled_host_timer_active=0;
        local_oled_recover(2,0);
        return SF_DONE;
    }
    timer->waketime=now+timer_from_us(100000);
    return SF_RESCHEDULE;
}
static void oled_host_shutdown(void) {
    // sched_timer_reset() has already removed timers in DECL_SHUTDOWN.
    oled_host_owned=oled_host_timer_active=0;
}
void command_m300_oled_host(uint32_t *args) {
    uint32_t state=args[0];
    if(state>2)shutdown("M300 invalid OLED host lease");
    oled_host_protocol=1;
    if(!state) {
        irqstatus_t flag=irq_save();
        if(oled_host_timer_active)sched_del_timer(&oled_host_timer);
        oled_host_timer_active=0;
        oled_host_owned=0;
        irq_restore(flag);
        local_oled_recover(panel_fault ? 3 : 1,0);
    } else if(!panel_fault && !oled_display_fault && (state==1 || oled_host_owned)) {
        if(state==1) {
            // A new claim is a full display transaction boundary. This is
            // command/task context, so live timers may be cancelled here.
            // Do not let an old DMA ACK or pending local redraw cross it.
            oled_dma_cancel_alarm();
            oled_dma_shutdown();
            local_oled_cancel();
            panel_put(GPIOB,12,1);
            panel_put(GPIOE,9,0);
            panel_put(GPIOE,10,0);
        }
        // Heartbeat (2) cannot revive an expired/released display session.
        irqstatus_t flag=irq_save();
        oled_host_owned=1;
        oled_host_seen=timer_read_time();
        if(!oled_host_timer_active) {
            oled_host_timer.func=oled_host_event;
            oled_host_timer.waketime=oled_host_seen+timer_from_us(100000);
            oled_host_timer_active=1;
            sched_add_timer(&oled_host_timer);
        }
        irq_restore(flag);
    }
    sendf("m300_oled_host_state state=%c local=%c fault=%c reason=%c",
          oled_host_owned,local_state,(panel_fault || oled_display_fault),local_reason);
}
DECL_COMMAND_FLAGS(command_m300_oled_host,HF_IN_SHUTDOWN,"m300_oled_host state=%c");

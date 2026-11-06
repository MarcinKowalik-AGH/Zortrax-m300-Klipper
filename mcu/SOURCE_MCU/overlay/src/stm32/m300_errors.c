// SPDX-License-Identifier: GPL-3.0-or-later
// Error metadata only. No GPIO, timers, ADC ownership, flash or actuator API.
#ifndef M300_ERRORS_TEST
#include "autoconf.h"
#include "board/irq.h"
#include "command.h"
#include "sched.h"
#endif
#include "m300_errors.h"
#include "m300_error_catalog.inc"

DECL_CONSTANT("M300_ERROR_ABI", 1);
DECL_CONSTANT("M300_OEM_ERROR_COUNT", 21);
static struct m300_error_state error_state;

const struct m300_error_text *
m300_error_text(uint16_t code, uint8_t kind)
{
    if (code)
        for (unsigned i = 0; i < sizeof(error_codes)/sizeof(error_codes[0]); i++)
            if (error_codes[i].code == code)
                return &error_codes[i];
    if (kind >= sizeof(error_native)/sizeof(error_native[0]))
        kind = M300_ERROR_SHUTDOWN;
    return &error_native[kind];
}

static uint8_t valid_code(uint16_t code)
{
    return !code || m300_error_text(code, M300_ERROR_NONE)->code == code;
}

void m300_error_snapshot(struct m300_error_state *state)
{
    irqstatus_t flag = irq_save();
    *state = error_state;
    irq_restore(flag);
}

void m300_error_capture(uint16_t code, uint8_t kind)
{
    // Called only on an actual fault, not on the healthy ADC / STEP path.
    irqstatus_t flag = irq_save();
    if (!error_state.fatal) {
        error_state.code = code;
        error_state.kind = kind;
        error_state.source = 2; // Local MCU diagnosis.
        error_state.fatal = 1;
        error_state.revision++;
    }
    irq_restore(flag);
}

void m300_error_shutdown(uint16_t native_id)
{
    uint8_t kind = M300_ERROR_SHUTDOWN;
    if (native_id == _DECL_STATIC_STR("Timer too close"))
        kind = M300_ERROR_TIMER;
    else if (native_id == _DECL_STATIC_STR("Stepper too far in past"))
        kind = M300_ERROR_STEPPER;
    else if (native_id == _DECL_STATIC_STR("ADC out of range"))
        kind = M300_ERROR_SENSOR;
    m300_error_capture(0, kind); // Replaces an old, nonfatal file notice.
    if (!error_state.native_id)
        error_state.native_id = native_id;
}

void command_m300_error_query(uint32_t *args)
{
    (void)args;
    struct m300_error_state state;
    m300_error_snapshot(&state);
    sendf("m300_error_state code=%hu kind=%c fatal=%c source=%c native_id=%hu revision=%u",
          state.code, state.kind, state.fatal, state.source, state.native_id,
          state.revision);
}
DECL_COMMAND_FLAGS(command_m300_error_query, HF_IN_SHUTDOWN, "m300_error_query");

void command_m300_error_set(uint32_t *args)
{
    uint16_t code = args[0];
    uint8_t kind = args[1], fatal = args[2];
    if (args[0] != code || !valid_code(code) || args[1] > M300_ERROR_GUARD
        || args[2] > 1 || (fatal && !code && kind == M300_ERROR_NONE))
        return;
    irqstatus_t flag = irq_save();
    // Acknowledge clears only a live, nonfatal notice. An unknown native
    // shutdown may acquire a precise host explanation; a local specific
    // root cause cannot be replaced by a later host consequence.
    uint8_t specific = error_state.code || (error_state.kind != M300_ERROR_SHUTDOWN
                                            && error_state.kind != M300_ERROR_GUARD);
    uint8_t incoming_specific = code || (kind != M300_ERROR_SHUTDOWN
                                         && kind != M300_ERROR_GUARD);
    if ((!fatal && (error_state.fatal || sched_is_shutdown()))
        || (error_state.fatal && (specific || !incoming_specific))) {
        irq_restore(flag);
        return;
    }
    if (error_state.code != code || error_state.kind != kind || error_state.fatal != fatal) {
        error_state.code = code;
        error_state.kind = kind;
        error_state.fatal = fatal;
        error_state.source = code || kind ? 1 : 0;
        error_state.revision++;
    }
    irq_restore(flag);
}
DECL_COMMAND_FLAGS(command_m300_error_set, HF_IN_SHUTDOWN,
                   "m300_error_set code=%hu kind=%c fatal=%c");

#ifndef __STM32_M300_ERRORS_H
#define __STM32_M300_ERRORS_H
#include <stdint.h>

enum m300_error_kind {
    M300_ERROR_NONE, M300_ERROR_SHUTDOWN, M300_ERROR_TIMER, M300_ERROR_STEPPER,
    M300_ERROR_LINK, M300_ERROR_ESTOP, M300_ERROR_PLATFORM, M300_ERROR_SENSOR,
    M300_ERROR_GUARD
};
struct m300_error_state {
    uint16_t code, native_id;
    uint8_t kind, fatal, source;
    uint32_t revision;
};
struct m300_error_text {
    uint16_t code;
    uint8_t icon;
    const char *title, *hint1, *hint2;
};
void m300_error_capture(uint16_t code, uint8_t kind);
void m300_error_shutdown(uint16_t native_id);
void m300_error_snapshot(struct m300_error_state *state);
const struct m300_error_text *m300_error_text(uint16_t code, uint8_t kind);
void m300_error_adc(void *adc, uint32_t channel);
#endif

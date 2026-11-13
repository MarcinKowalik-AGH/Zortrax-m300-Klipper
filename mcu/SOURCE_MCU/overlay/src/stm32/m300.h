#ifndef __STM32_M300_H
#define __STM32_M300_H
// Classic Zortrax M300 P01 board policy. GPL-3.0-or-later.
// Protocol ABI belongs to M300_CLASSIC, not the Inventure board family.
#include <stdint.h>

#define M300_ABI 1
#define M300_ARM_MAGIC 0x4d333031u
#define M300_GATE_MOTION 1
#define M300_GATE_HEAT 2
// Unqualified P01 policy caps derived from the audited stock conversion/LUT.
// Host ranges may narrow these caps, never widen them through the protocol.
#define M300_HOT_RAW_MAX 1941u
#define M300_BED_RAW_MIN 1741u
#define M300_BED_RAW_MAX 3941u

enum m300_fault {
    M300_FAULT_NONE = 0,
    M300_FAULT_HEARTBEAT = 1,
    M300_FAULT_ADC_STALE = 2,
    M300_FAULT_PLATFORM = 3,
    M300_FAULT_ADC_RANGE = 4,
    M300_FAULT_DISARM = 5,
    M300_FAULT_CONFIG = 6,
    M300_FAULT_ARM = 7,
    M300_FAULT_PIN = 8,
    M300_FAULT_REQUEST = 9,
    M300_FAULT_SHUTDOWN = 255,
};

void m300_early_init(void);
int m300_factory_write_allowed(void);
int m300_factory_runtime_allowed(uint32_t blocked_ticks);
int m300_factory_led_pin(const void *regs, uint32_t bit);
int m300_factory_heater_pin(const void *regs, uint32_t bit);
void m300_factory_platform_fault(void);
void m300_check_pin_mode(uint32_t pin, uint32_t mode);
void m300_check_native_input(uint32_t pin);
uint32_t m300_filter_gpio(void *regs, uint32_t bit, uint32_t val);
uint32_t m300_toggle_gpio(void *regs, uint32_t bit);
void m300_adc_observe(void *adc, uint32_t channel, uint16_t value);
void m300_require_motion(void);
void m300_require_motion_gate(void);
void m300_require_output(void *regs, uint32_t bit, uint32_t on);
void m300_check_output_defaults(uint32_t pin, uint32_t value,
                                uint32_t default_value);

#endif

#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministically apply the classic-M300 P01 overlay to pinned Klipper.

Accepts a clean checkout or the official source ZIP extracted by build.py.
This is a source transformation only: no compiler, network, git mutation,
bootloader command, flash write, or permission escalation is performed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

PIN = "ee2c6fb6b00b2b5d097ef70d0868df7d74943b51"
KIT = Path(__file__).resolve().parents[1]
ARCHIVE_SHA256 = "fe4c6a25c370c32f519a008e46e14612ddb116a5ac135146afeee7d0bc4c2bf0"
VERSION = "M300_CLASSIC-1.0.3"
MARKER = ".m300-p01-patch.json"
EXPECTED = {
    "scripts/buildcommands.py": "b67abb120a4d283af722dd1fc28c1317836510cc426cda4d917ad2548c645b44",
    "src/basecmd.c": "c91c423e08662a642108bb79a3377a312e47c11e4f7178e19e11734a1e874f79",
    "src/sched.c": "61c00658d8bb829f1e0344adf3e47939deea7f972381e8928e228fd168fab94b",
    "src/adccmds.c": "708e25a6ba5dfe93b1556c7bca0c7113676b84cca1a46f31c2d6e669b998a04d",
    "src/stm32/serial.c": "feea757d96f50203874ead8c89dd5b9488150986b46ef0180cf658f37c7d2650",
    "src/Kconfig": "b085a73a30c492ff0185b57b17e0ca9e7e52a45d4ab5d853fde8030486e6a072",
    "src/stm32/Kconfig": "35891c81db96beecf45914b9e124cb748d0e4fe252b97883a4eb18d9674df817",
    "src/stm32/Makefile": "5047f8c0edcb12bcafaff88bc24971229f48cc9f5c9a12065f6cb6d2c8414f46",
    "src/stm32/stm32f1.c": "57a416e3fe5d18096217a764b3c3297d8fa5c75f14c5c0febdbd69bfd851fef3",
    "src/stm32/gpio.c": "a795200fcff149df6adba4bff8075ed2d79d4bb45a388d0d423fa9534db7cc3d",
    "src/stm32/adc.c": "b39c9d4fdc9d9c59441665c0d4541e52f7c038df0cd783598479e27becd735b4",
    "src/gpiocmds.c": "3609c78951bda4bc25c4bde279f0ff64c3b94414ef06ff47dd24ce3f2bc51bcf",
    "src/stepper.c": "09326367a812d02b4499a75351abcdd412075330b6c282c340a2c5003ca840c5",
    "src/debugcmds.c": "4a89dbdc7a6ea222d8ca60e2ee10028900381c6ccffc5c167292053e95681aea",
    "scripts/check-gcc.sh": "56ce004eef5d2561c1e3e13a01baa4026c46630e47e3096d457343812d8ed434",
    "src/generic/armcm_link.lds.S": "a82002cba58573cdeb37775863ad6134986972b968195fd406232aab68a7cdb0",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    found = text.count(old)
    if found != count:
        raise ValueError(f"{label}: expected {count} exact anchors, found {found}")
    return text.replace(old, new)


def transformed(files: dict[str, str]) -> dict[str, str]:
    """Check all anchors and form the complete change in memory before writing."""
    f = dict(files)
    key = "src/Kconfig"
    f[key] = replace(f[key], "    depends on HAVE_LIMITED_CODE_SIZE\n",
                     "    depends on HAVE_LIMITED_CODE_SIZE || M300_CLASSIC\n",
                     key + ":feature-menu")
    key = "src/stm32/Kconfig"
    anchor = 'config BOARD_DIRECTORY\n    string\n    default "stm32"\n'
    f[key] = replace(f[key], anchor, anchor + '''
config M300_CLASSIC
    bool "Classic Zortrax M300 P01 LAB guard"
    depends on MACH_STM32F103
    default n
    help
        Fixed classic-M300 board ownership and local safety, ABI 1.
        Requires 72 MHz, USART1 PA9/PA10, 32 KiB stock bootloader offset.
        Starts unarmed with both cooling fans HIGH; never flashes the board.

config M300_XY_STEP_TIMER
    bool "Classic M300 constant-period XY STEP timer"
    depends on M300_CLASSIC && !WANT_STEPPER_OPTIMIZED_BOTH_EDGE
    default y
''', key)

    key = "src/stm32/Makefile"
    anchor = "# Add source files\n"
    f[key] = replace(f[key], anchor, anchor + '''src-$(CONFIG_M300_CLASSIC) += stm32/m300_board.c stm32/m300_panel.c stm32/m300_sd.c stm32/m300_uart.c stm32/m300_factory.c stm32/m300_factory_counter.c stm32/m300_errors.c
src-$(CONFIG_M300_XY_STEP_TIMER) += stm32/m300_xy_step_timer.c
ifeq ($(CONFIG_M300_CLASSIC),y)
CFLAGS_klipper.elf += -Wl,-Map=$(OUT)klipper.map
endif
''', key)

    key = "src/basecmd.c"
    anchor = '#include <string.h> // memset\n'
    f[key] = replace(f[key], anchor, anchor + '#include "autoconf.h"\n',
                     key + ":m300-include")
    anchor = "static uint8_t oid_count;\n"
    f[key] = replace(f[key], anchor, anchor + '''
#if CONFIG_M300_CLASSIC
// OEM NVM Flash can stall native timers even while the M300 board is
// unarmed. Refuse the write once native object configuration has begun.
int
m300_native_config_started(void)
{
    return oids != NULL || is_finalized();
}
#endif
''', key + ":m300-write-window")

    key = "src/stm32/serial.c"
    f[key] = replace(f[key], '#include "internal.h" // enable_pclock\n',
                     '#include "internal.h" // enable_pclock\n#if CONFIG_M300_CLASSIC\n#include "m300_uart.h"\n#endif\n', key + ":include")
    f[key] = replace(f[key], 'uint32_t div = DIV_ROUND_CLOSEST(pclk, CONFIG_SERIAL_BAUD);',
                     'uint32_t baud = CONFIG_SERIAL_BAUD;\n#if CONFIG_M300_CLASSIC\n    baud = m300_uart_baud();\n#endif\n    uint32_t div = DIV_ROUND_CLOSEST(pclk, baud);', key + ":baud")

    # Capture the original cause without SPI/serial/actuator work.
    key = "src/sched.c"
    anchor = '#include "command.h" // shutdown\n'
    f[key] = replace(f[key], anchor, anchor + '''#if CONFIG_M300_CLASSIC
#include "board/m300_errors.h"
#endif
''', key + ":error-include")
    anchor = "static struct timer sentinel_timer = {\n"
    f[key] = replace(f[key], anchor, '''#if CONFIG_M300_CLASSIC
int32_t
m300_factory_periodic_margin(void)
{
    return (int32_t)(periodic_timer.waketime - timer_read_time());
}
#endif

''' + anchor, key + ":factory-flash-timing")
    anchor = '    SchedStatus.shutdown_status = 2;\n    sched_timer_reset();\n'
    f[key] = replace(f[key], anchor, '''    SchedStatus.shutdown_status = 2;
#if CONFIG_M300_CLASSIC
    m300_error_shutdown(SchedStatus.shutdown_reason);
#endif
    sched_timer_reset();
''', key + ":error-cause")

    key = "src/adccmds.c"
    anchor = '#include "sched.h" // DECL_TASK\n'
    f[key] = replace(f[key], anchor, anchor + '''#include "autoconf.h"
#if CONFIG_M300_CLASSIC
#include "board/m300_errors.h"
#endif
''', key + ":error-include")
    anchor = '            try_shutdown("ADC out of range");\n'
    f[key] = replace(f[key], anchor, '''#if CONFIG_M300_CLASSIC
            if (!sched_is_shutdown())
                m300_error_adc(a->pin.adc, a->pin.chan);
#endif
            try_shutdown("ADC out of range");
''', key + ":error-channel")

    # F103-specific startup and pin mode gate; no STM32F2/F4 code is changed.
    key = "src/stm32/stm32f1.c"
    anchor = '#include "sched.h" // sched_main\n'
    f[key] = replace(f[key], anchor, anchor + '''#if CONFIG_M300_CLASSIC
#include "m300.h"
#endif
#if CONFIG_M300_XY_STEP_TIMER
#include "m300_xy_step_timer.h"
#endif
''', key + ":include")
    anchor = "#define STM_OSPEED"
    f[key] = replace(f[key], anchor, '''#if CONFIG_M300_XY_STEP_TIMER
void
m300_xy_timer_remap(void)
{
    stm32f1_alternative_remap(AFIO_MAPR_TIM2_REMAP_Msk | AFIO_MAPR_TIM3_REMAP_Msk,
                              AFIO_MAPR_TIM2_REMAP_PARTIALREMAP1
                              | AFIO_MAPR_TIM3_REMAP_PARTIALREMAP);
}
#endif

''' + anchor, key + ":xy-timer-remap")
    anchor = "gpio_peripheral(uint32_t gpio, uint32_t mode, int pullup)\n{\n"
    f[key] = replace(f[key], anchor, anchor + '''#if CONFIG_M300_CLASSIC
    m300_check_pin_mode(gpio, mode);
#endif
''', key + ":mode")
    anchor = "    RCC->APB2ENR = 0;\n\n    // Setup clocks\n"
    f[key] = replace(f[key], anchor, '''    RCC->APB2ENR = 0;
#if CONFIG_M300_CLASSIC
    m300_early_init();
#endif

    // Setup clocks
''', key + ":early")

    # Every native GPIO write/reset/toggle passes the local board guard.
    key = "src/stm32/gpio.c"
    anchor = '#include <string.h> // ffs\n'
    f[key] = replace(f[key], anchor, anchor + '''#include "autoconf.h"
#if CONFIG_M300_CLASSIC
#include "m300.h"
#endif
''', key + ":include")
    anchor = "    irqstatus_t flag = irq_save();\n    if (val)\n"
    f[key] = replace(f[key], anchor, '''    irqstatus_t flag = irq_save();
#if CONFIG_M300_CLASSIC
    val = m300_filter_gpio(regs, g.bit, val);
#endif
    if (val)
''', key + ":reset")
    anchor = "    regs->ODR ^= g.bit;\n"
    f[key] = replace(f[key], anchor, '''#if CONFIG_M300_CLASSIC
    uint32_t val = m300_toggle_gpio(regs, g.bit);
    if (val)
        regs->BSRR = g.bit;
    else
        regs->BSRR = g.bit << 16;
#else
    regs->ODR ^= g.bit;
#endif
''', key + ":toggle")
    anchor = "gpio_out_write(struct gpio_out g, uint32_t val)\n{\n    GPIO_TypeDef *regs = g.regs;\n"
    f[key] = replace(f[key], anchor, anchor + '''#if CONFIG_M300_CLASSIC
    irqstatus_t flag = irq_save();
    val = m300_filter_gpio(regs, g.bit, val);
#endif
''', key + ":write-start")
    anchor = "        regs->BSRR = g.bit << 16;\n}\n\n\nstruct gpio_in\n"
    f[key] = replace(f[key], anchor, '''        regs->BSRR = g.bit << 16;
#if CONFIG_M300_CLASSIC
    irq_restore(flag);
#endif
}


struct gpio_in
''', key + ":write-end")
    anchor = "    int pin = regs_to_pin(regs, g.bit);\n    irqstatus_t flag = irq_save();\n    gpio_peripheral(pin, GPIO_INPUT, pull_up);\n"
    f[key] = replace(f[key], anchor, '''    int pin = regs_to_pin(regs, g.bit);
#if CONFIG_M300_CLASSIC
    m300_check_native_input(pin);
#endif
    irqstatus_t flag = irq_save();
    gpio_peripheral(pin, GPIO_INPUT, pull_up);
''', key + ":input")

    # Observe only a completed conversion. Cancellation of an in-flight ADC
    # must not count its old DR value as a fresh temperature observation.
    key = "src/stm32/adc.c"
    anchor = '#include "sched.h" // sched_shutdown\n'
    f[key] = replace(f[key], anchor, anchor + '''#if CONFIG_M300_CLASSIC
#include "m300.h"
#endif
''', key + ":include")
    anchor = "    adc->SR = ~ADC_SR_STRT;\n    return adc->DR;\n"
    f[key] = replace(f[key], anchor, '''#if CONFIG_M300_CLASSIC
    uint32_t valid = (adc->SR & ADC_SR_EOC) && adc->SQR3 == g.chan;
#endif
    adc->SR = ~ADC_SR_STRT;
    uint16_t value = adc->DR;
#if CONFIG_M300_CLASSIC
    if (valid)
        m300_adc_observe(adc, g.chan, value);
#endif
    return value;
''', key + ":observe")

    # Reject native actuator queues submitted while unarmed. Merely masking
    # the eventual GPIO edge would leave a pre-arm queue latent after arming.
    key = "src/stepper.c"
    anchor = '#include "autoconf.h" // CONFIG_*\n'
    f[key] = replace(f[key], anchor, anchor + '''#if CONFIG_M300_CLASSIC
#include "board/m300.h"
#endif
#if CONFIG_M300_XY_STEP_TIMER
#include "board/m300_xy_step_timer.h"
#endif
''', key + ":include")
    anchor = "    uint8_t flags : 8;\n};\n"
    f[key] = replace(f[key], anchor, '''    uint8_t flags : 8;
#if CONFIG_M300_XY_STEP_TIMER
    uint8_t timer_axis, timer_mode;
    uint32_t timer_first_clock;
#endif
};
''', key + ":xy-timer-fields")
    anchor = "// Setup a stepper for the next move in its queue\n"
    f[key] = replace(f[key], anchor, '''#if CONFIG_M300_XY_STEP_TIMER
enum { M300_TIMER_SOFTWARE, M300_TIMER_PLANNED, M300_TIMER_RUNNING };

static void
m300_stepper_prepare_timer(struct stepper *s)
{
    if (!s->timer_axis || s->add
        || !m300_xy_timer_eligible(s->interval, s->step_pulse_ticks, s->count / 2))
        return;
    s->timer_mode = M300_TIMER_PLANNED;
    s->timer_first_clock = s->time.waketime;
    // Allow a short setup window when scheduling from a previous block.
    // Keep new timers inserted by a host command strictly in the future.
    if ((int32_t)(s->time.waketime - timer_read_time()) > 208)
        s->time.waketime -= 104;
}
#endif

''' + anchor, key + ":xy-timer-prepare")
    anchor = "                s->time.waketime = min_next_time;\n            return SF_RESCHEDULE;\n"
    f[key] = replace(f[key], anchor, '''                s->time.waketime = min_next_time;
#if CONFIG_M300_XY_STEP_TIMER
            m300_stepper_prepare_timer(s);
#endif
            return SF_RESCHEDULE;
''', key + ":xy-timer-dir-handoff")
    anchor = "    if (need_dir_change)\n        gpio_out_toggle_noirq(s->dir_pin);\n    return SF_RESCHEDULE;"
    f[key] = replace(f[key], anchor, '''    if (need_dir_change)
        gpio_out_toggle_noirq(s->dir_pin);
#if CONFIG_M300_XY_STEP_TIMER
    m300_stepper_prepare_timer(s);
#endif
    return SF_RESCHEDULE;''', key + ":xy-timer-handoff")
    anchor = "stepper_event_full(struct timer *t)\n{\n    struct stepper *s = container_of(t, struct stepper, time);\n"
    f[key] = replace(f[key], anchor, anchor + '''#if CONFIG_M300_XY_STEP_TIMER
    const uint32_t high_margin = M300_XY_TIMER_HIGH_MARGIN;
    const uint32_t gate_margin = M300_XY_TIMER_GATE_MARGIN;
    if (s->timer_mode == M300_TIMER_PLANNED) {
        uint32_t count = s->count / 2;
        uint32_t span = (count - 1) * s->interval;
        uint32_t first = m300_xy_timer_start(s->timer_axis, s->interval,
                                         s->step_pulse_ticks, count,
                                         s->timer_first_clock);
        s->timer_mode = M300_TIMER_RUNNING;
        s->next_step_time += span;
        s->time.waketime = first + span + s->step_pulse_ticks
            + high_margin + gate_margin;
        return SF_RESCHEDULE;
    }
    if (s->timer_mode == M300_TIMER_RUNNING) {
        struct move_node *node = move_queue_first(&s->mq);
        if (node) {
            struct stepper_move *m = container_of(node, struct stepper_move,
                                                  node);
            uint32_t period = m->interval, count = m->count;
            if (!(m->flags & MF_DIR) && !m->add
                && m300_xy_timer_eligible(period, s->step_pulse_ticks, count)) {
                uint32_t first = s->next_step_time + period;
                // Preserve the minimum low width if the previous block ran
                // late. Otherwise re-anchor to Klipper's absolute clock.
                uint32_t earliest = s->time.waketime
                    + s->step_pulse_ticks - gate_margin;
                if (timer_is_before(first, earliest))
                    first = earliest;
                first = m300_xy_timer_chain(s->timer_axis, period, count, first);
                s->next_step_time += period * count;
                s->time.waketime = first + period * (count - 1)
                    + s->step_pulse_ticks + high_margin + gate_margin;
                s->position += count;
                s->interval = period;
                s->count = 2 * count;
                move_free(move_queue_pop(&s->mq));
                return SF_RESCHEDULE;
            }
        }
        m300_xy_timer_finish(s->timer_axis);
        s->timer_mode = M300_TIMER_SOFTWARE;
        s->time.waketime += s->step_pulse_ticks;
        return stepper_load_next(s);
    }
#endif
''', key + ":xy-timer-step")
    anchor = "    s->step_pulse_ticks = args[4];\n"
    f[key] = replace(f[key], anchor, anchor + '''#if CONFIG_M300_XY_STEP_TIMER
    if (invert_step == 0)
        s->timer_axis = m300_xy_timer_axis(args[1]);
#endif
''', key + ":xy-timer-config")
    anchor = "    uint32_t position = s->position;\n"
    f[key] = replace(f[key], anchor, anchor + '''#if CONFIG_M300_XY_STEP_TIMER
    if (s->timer_mode == M300_TIMER_RUNNING)
        position -= m300_xy_timer_remaining(s->timer_axis);
    else
#endif
''', key + ":xy-timer-position")
    anchor = "    sched_del_timer(&s->time);\n    s->next_step_time"
    f[key] = replace(f[key], anchor, '''    sched_del_timer(&s->time);
#if CONFIG_M300_XY_STEP_TIMER
    if (s->timer_mode == M300_TIMER_RUNNING)
        s->count = 2 * m300_xy_timer_stop(s->timer_axis);
    s->timer_mode = M300_TIMER_SOFTWARE;
#endif
    s->next_step_time''', key + ":xy-timer-stop")
    anchor = "stepper_shutdown(void)\n{\n"
    f[key] = replace(f[key], anchor, anchor + '''#if CONFIG_M300_XY_STEP_TIMER
    m300_xy_timer_abort_all();
#endif
''', key + ":xy-timer-shutdown")
    anchor = "command_queue_step(uint32_t *args)\n{\n"
    f[key] = replace(f[key], anchor, anchor + '''#if CONFIG_M300_CLASSIC
    m300_require_motion();
#endif
''', key + ":queue")

    key = "src/gpiocmds.c"
    anchor = '#include "basecmd.h" // oid_alloc\n'
    f[key] = replace(f[key], anchor, '''#include "autoconf.h"
#if CONFIG_M300_CLASSIC
#include "board/m300.h"
#endif
''' + anchor, key + ":include")
    anchor = "command_config_digital_out(uint32_t *args)\n{\n"
    f[key] = replace(f[key], anchor, anchor + '''#if CONFIG_M300_CLASSIC
    m300_check_output_defaults(args[1], args[2], args[3]);
#endif
''', key + ":defaults")
    anchor = "command_queue_digital_out(uint32_t *args)\n{\n    struct digital_out_s *d = oid_lookup(args[0], command_config_digital_out);\n"
    f[key] = replace(f[key], anchor, anchor + '''#if CONFIG_M300_CLASSIC
    m300_require_output(d->pin.regs, d->pin.bit, args[2]);
#endif
''', key + ":queue")
    anchor = "command_update_digital_out(uint32_t *args)\n{\n    struct digital_out_s *d = oid_lookup(args[0], command_config_digital_out);\n"
    f[key] = replace(f[key], anchor, anchor + '''#if CONFIG_M300_CLASSIC
    m300_require_output(d->pin.regs, d->pin.bit, args[1]);
#endif
''', key + ":update")
    anchor = "command_set_digital_out(uint32_t *args)\n{\n"
    f[key] = replace(f[key], anchor, anchor + '''#if CONFIG_M300_CLASSIC
    m300_check_output_defaults(args[0], args[1], 0);
#endif
''', key + ":set")

    # Arbitrary MMIO read/write commands would bypass every board ownership and
    # safety hook, including during shutdown. Keep only protocol ping/nop.
    key = "src/debugcmds.c"
    anchor = '#include "board/io.h" // readl\n'
    f[key] = replace(f[key], anchor, '#include "autoconf.h"\n' + anchor, key + ":include")
    anchor = "void\ncommand_debug_read(uint32_t *args)\n"
    f[key] = replace(f[key], anchor, "#if !CONFIG_M300_CLASSIC\n" + anchor, key + ":disable-start")
    anchor = "void\ncommand_debug_ping(uint32_t *args)\n"
    f[key] = replace(f[key], anchor, "#endif // !CONFIG_M300_CLASSIC\n\n" + anchor, key + ":disable-end")

    # Use the matching binutils for the GCC ABI check on non-ARM build hosts.
    key = "scripts/check-gcc.sh"
    f[key] = replace(f[key], "readelf -A", "arm-none-eabi-readelf -A", key, 2)

    key = "src/generic/armcm_link.lds.S"
    f[key] += '''
#if CONFIG_M300_CLASSIC
ASSERT(ORIGIN(rom) == 0x08008000, "M300 stock bootloader boundary")
ASSERT(ORIGIN(rom) + LENGTH(rom) <= 0x0803a000, "M300 protected stock flash")
ASSERT(_data_flash + SIZEOF(.data) <= 0x0803a000, "M300 image overlaps stock data")
ASSERT(_bss_end <= _stack_start, "M300 static data overlaps reserved stack")
#endif
'''
    # The ordinary Klipper MCU dictionary uses ?-timestamp-hostname in an
    # exported source archive. Override only the M300 build, while keeping
    # the upstream behavior for builds without M300_FIRMWARE_VERSION.
    key = "scripts/buildcommands.py"
    anchor = "    return version + extra\n"
    f[key] = replace(f[key], anchor, '''    fixed = os.environ.get("M300_FIRMWARE_VERSION")
    if fixed:
        if fixed != "1.0.3":
            error("Unsupported M300 firmware version")
        return fixed
    return version + extra
''', key + ":clean-mcu-version")
    return f


def patch(root: Path) -> dict:
    root = Path(root).resolve()
    overlay = {str(p.relative_to(KIT / "overlay")): p.read_bytes()
               for p in sorted((KIT / "overlay").rglob("*")) if p.is_file()
               and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    if not {"src/stm32/m300_board.c", "src/stm32/m300_panel.c", "src/stm32/m300_sd.c", "src/stm32/m300.h"} <= overlay.keys():
        raise ValueError("Incomplete M300 MCU overlay")
    marker = root / MARKER
    if marker.exists():
        existing = json.loads(marker.read_text())
        if existing.get("version") != VERSION or existing.get("upstream_commit") != PIN:
            raise ValueError("Different overlay already applied; start from a clean source copy")
        if existing.get("overlay_sha256") != {k: sha(v) for k, v in overlay.items()}:
            raise ValueError("Overlay changed since application; rebuild a fresh private copy")
        for rel, digest in existing["patched_sha256"].items():
            path = root / rel
            if not path.is_file() or sha(path.read_bytes()) != digest:
                raise ValueError("Patched source modified: " + rel)
        return existing
    if (root / ".git").exists():
        head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        if head != PIN:
            raise ValueError("Wrong upstream git revision")
    owner = root / ".m300-build-owner.json"
    if owner.exists():
        provenance = json.loads(owner.read_text())
        if provenance.get("archive_sha256") != ARCHIVE_SHA256 or provenance.get("upstream_commit") != PIN:
            raise ValueError("Wrong source archive provenance")
    original = {}
    for rel, digest in EXPECTED.items():
        path = root / rel
        if not path.is_file() or sha(path.read_bytes()) != digest:
            raise ValueError("Not the pristine pinned source: " + rel)
        original[rel] = path.read_text()
    changed = {rel: text.encode() for rel, text in transformed(original).items()}
    for rel, data in overlay.items():
        target = root / rel
        if target.exists():
            raise ValueError("Overlay would overwrite an existing source: " + rel)
        if rel in changed:
            raise ValueError("Overlay collides with a transformed source: " + rel)
        changed[rel] = data
    # All source/hash/anchor/collision checks have succeeded before first write.
    for rel, data in changed.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    result = {
        "version": VERSION, "upstream_commit": PIN,
        "official_archive_sha256": ARCHIVE_SHA256,
        "source_verification": "exact SHA-256 of every transformed upstream file",
        "original_sha256": EXPECTED,
        "overlay_sha256": {rel: sha(data) for rel, data in overlay.items()},
        "patched_sha256": {rel: sha(data) for rel, data in changed.items()},
    }
    marker.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    result = patch(args.root)
    print(f"{result['version']}: verified/applied to {args.root.resolve()}")


if __name__ == "__main__":
    main()

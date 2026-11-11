# v1.0.0-beta.12 — faster, half-width OLED preview in Fluidd

Applies to **Zortrax M300 Classic**, host R16.12, Fluidd 1.37.7.
Supersedes beta.11 and includes all previously verified homing, calibration,
bed mesh, buzzer, OLED font/logo and error-procedure fixes.

## Fix for user-observed lag

The beta.11 preview serialized only `stream.previous`, the most recent
**fully acknowledged** physical OLED frame. Waiting for completion of
the full OLED transfer and then the mirror's additional 500 ms publication
interval made the web preview appear much later than knob navigation.
It was correct as an ACK-confirmed observation but unsuitable as a
low-latency UI display.

Beta.12 observes Klipper's **already-rendered 256×64 4-bit frame**
`m300_oled._render_wire`. This removes the extra full-frame
transfer/ACK wait **from the Fluidd preview only**. Frame publication is
coalesced with no queue: when multiple knob moves happen between
status updates, only the latest rendered frame is compressed.
The minimum interval is 125 ms, and the indexed 4-bit PNG uses
fast zlib level 1. The existing Moonraker status subscription determines
the effective refresh cadence (usually ~250 ms, hence ~4 Hz).
No extra MCU query, screen render, buzzer/G-code action or web port is added.

**Important:** an image shown by Fluidd may now be ahead of the physical
OLED if an SPI/DMA transfer is still in progress. The preview must not be
used as evidence of physical display ACK or permission to execute a menu
action. The physical OLED retains the original independently verified
RLE, differential windows, SPI DMA, UART, ACK and timeout recovery.

## Size and behavior

The OLED image and disconnected placeholder use 50% of the Temperature
card's content width, centered directly beneath the temperature graph.
It remains a read-only, collapsible widget with its exact 4:1 aspect
ratio, all 16 grayscale levels and an offline state. On non-M300
printers it remains hidden.

## Installation

Update only when the printer is **idle** and Klipper state is **Ready**:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

After installation, hard-refresh Fluidd (Cmd+Shift+R on macOS).
**No MCU firmware or bootloader flash is required.**

## Quality gates

The full GitHub Actions build checks **700 host regressions**, including
rapid frame coalescing, unchanged 4-bit luminance, invalid/offline image
rejection and 125 ms publication bound, nine repository contracts,
existing homing/PC7/bed mesh/thermal/print procedures, native Klippy
FILEOUTPUT, STM32F103 firmware compilation, OLED ACK/RLE transport,
TypeScript, ESLint, frontend tests, production Fluidd build,
transactional deployment and release package checksums.

Physical Orange Pi/browser latency must be confirmed by measuring
the deployed hardware; the tests cannot guarantee a specific reaction
time under an arbitrary network or printer workload.

# v1.0.0-beta.8 — original Klipper logo and bounded menu beeps

Target: Zortrax M300 Classic, STM32F103, existing Host R16.12 / MCU R14.18.
Supersedes beta.7. Earlier fixes remain: beta.7 safe module migration,
beta.6 Cartesian menu and remembered cursor, beta.5 Bed Mesh chart and
beta.4 OLED ACK recovery. No firmware/bootloader reflash required.

## Official Klipper logo

The `Klipper` menu icon now shows the genuine Klipper V/nozzle mark rather
than an unrelated plain K. The source is the official
[Klipper3d/klipper `docs/img/klipper.svg`](https://github.com/Klipper3d/klipper/blob/master/docs/img/klipper.svg)
under GPL-3.0. The display-only native host module
`m300_klipper_logo.py` converts the official two paths to a single bright
50×50 monochrome silhouette on the existing project panel. The moving top
toolhead and the four 500 ms frames are retained. The archived original
sprite bank is not rewritten; the obsolete K is erased only in the
runtime frame, preserving independently audited historical assets.
[SVG reference](../assets/menu-symbols/klipper-official-mark-50.svg).

## Consistent short and long audio feedback

Formerly `m300_maintenance.click()` set the buzzer for 50 ms but the
only expiry fallback was the maintenance/LED tick. Native idle ticks occur
every 500 ms, so the audible pulse could greatly exceed 50 ms.

- Enter/select and ordinary exit: short 35 ms pulse.
- A current, visible and action-matched `Back` or `Up` row: 140 ms pulse.
- No different sounds for individual menu pages. A sound-disabled setting
  immediately cancels any active pulse and keeps future navigation silent.

Buzzer turnoff now has an independent reactor deadline. No new MCU polling,
pin ownership, PWM frequency, motion/thermal state, or screen transport
is introduced; the existing `m300_buzzer` output remains the sole owner.
Disconnect/shutdown invalidates pending buzzer timers. Stale action tokens
never qualify for the longer Back sound.

## Installation on the existing Orange Pi

With Klipper Ready and the printer idle:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Reload the Fluidd tab after installation. MCU R14.18 and original bootloader
remain unchanged. The update is intentionally refused if the host runtime
has unrelated unknown local modifications.

## Validation scope

The successful release build must pass 683 host tests, existing
beta.4–beta.7 migration evidence, OLED native frame and beep tests,
9 repository checks, MCU ARM build, pinned Klippy FILEOUTPUT scenarios,
Fluidd build and archive checksums. These verify software correctness, not
the exact audible durations measured on the physical printer's buzzer;
final verification is performed by navigating the OLED.

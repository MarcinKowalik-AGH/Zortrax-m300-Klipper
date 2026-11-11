# v1.0.0-beta.10 — OEM-scale graphics on host and MCU

**Printer:** original Zortrax M300 Classic with an existing compatible
STM32F103 bootloader, Klipper Host R16.12. This release supersedes beta.9.

## Changes

The full three-tone Klipper logo (7/11/15 luminance with lower-case
"klipper" wordmark) remains inside the original 50×50 printer icon.
Its obsolete 3px square/line animation **below the platform** has been
removed from the runtime 4bpp overlay, and the platform is now
**static and two pixels thick**. The moving top toolhead remains in
the original four-frame / 500ms cycle.

The Cartesian Home X/Y/Z/XY/XYZ and Move X/Y/Z icon frames are consistently
two pixels thick at full brightness (15), with non-active axes at level 9.
All icons still fit the exact 50×50 recovered firmware sprite footprint.
These are presentation-only changes; no G-code or motion timing was altered.

## What changed in MCU and what did not

On the M300 the **Orange Pi** renders the interactive main/OLED menu,
not the microcontroller. The MCU transmits its incoming 4bpp SSD1322 pixels
without converting them to binary. Its local renderer only owns emergency,
waiting and disconnected screens. The MCU source now uses named common
50×50, luminance 15 and divider luminance 5 constants for these local
screens and advertises `M300_OLED_NATIVE_GRAY4=1`. A native C/MCU SPI
test ensures the three levels 7/11/15 survive byte-for-byte.

The complete beta.10 archive therefore includes a fresh compiled MCU binary
from the validated source, **but MCU reflashing is not required** for the
normal Klipper menu improvements: the existing compatible MCU correctly
handles 4bpp already. We did not alter the stock original 37-icon sprite
archive, safety policy or MCU OLED ownership.

**As requested, buzzer operation has been left entirely unchanged** in
the host, MCU and configuration. Its previous 35/140ms timings remain
as installed. The upgrade does not modify buzzer timers or buzzer GPIO.

## Updating an existing Ready/idle M300

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

No motor/heater commands are issued by this update. Hard-refresh Fluidd
with Cmd+Shift+R after installation.

## Validation

Release publication requires **693 host tests**, nine repository tests,
GPIO/dictionary and MCU panel tests (including full 4bpp palette survival),
STM32F103 cross-build, pinned Klippy FILEOUTPUT runs, production Fluidd
build, transactional host packaging and SHA256 checksums. Physical OLED
brightness still needs confirmation on the connected M300.

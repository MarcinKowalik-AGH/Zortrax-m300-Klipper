# v1.0.0-beta.6 — Cartesian OLED menu and cursor return

For **Zortrax M300 Classic** only. This release supersedes v1.0.0-beta.5
and retains the earlier saved mesh chart, native printer controls, cooling,
OLED ACK recovery and all physical safety interlocks.

## Changes requested from actual OLED photographs

- Both **Klipper** and **Maintenance** now list **Home X, Home Y, Home Z,
  Home XY, Home XYZ** in precisely that order. The earlier "Homing ALL" name
  has become "Home XYZ". All entries call the same existing native homing
  operators; no new motion planner, velocity, motor GPIO or contact
  acquisition behavior was added.
- The Home Z label no longer includes "(180C)". The **actual 180°C minimum
  for Z contact homing is still enforced**, as are the original position and
  temperature safety guards.
- Five animated 50 x 50 OLED Cartesian icons blink the selected X, Y, Z,
  XY or XYZ axis arrows and letters. The selected X, Y or Z arrow likewise
  blinks on **Move X**, **Move Y** and **Move Z**, both on the navigation item
  and the corresponding movement subpage. The small nozzle animation above
  the platform remains, with no blinking square below the platform.
- Back and temperature-choice returns restore the previously selected row
  of the parent OLED menu. The remembered data is a display index only:
  no encoder receipt, action token, G-code command, motion state or heater
  target is cached. Reconnect invalidates the cursor cache.
- The original Print status graphic at source sprite `0x08020fb8`
  sometimes looks like part of a circle. It is artwork, **not** a numeric
  print progress indicator, and remains unchanged.

The checked-in vector design is
[`docs/assets/menu-symbols/m300-cartesian-preview.svg`](../assets/menu-symbols/m300-cartesian-preview.svg).
The installed OLED uses the new bounded four-frame **native 4bpp** renderer
(`m300_cartesian_graphics.py`), not SVG parsing. The original homing sprite
files are retained for provenance.

## Installation on an existing M300

With the machine idle and in Klipper Ready, on its Orange Pi:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

The installer transactionally transfers the new module with its updated
menu and tests. This update **does not require flashing the MCU** or changing
the bootloader, UART, homing temperature, travel or contact-plate geometry.

Do not perform the first physical homing unattended: independently check
the actual Z clearance and hardware state. The software tests are not an
in-person qualification of contact probing or motion on every printer.

## Validation and release integrity

Publication requires the successful GitHub Actions full Orange Pi build:
**678 host tests**, nine source/packaging contract tests, OLED artwork tests,
pinned Klippy FILEOUTPUT, ARM STM32F103, a reproducible production Fluidd
build and archive checksums. The versioned ZIP is published from exactly
the successful source commit; this release contains no physical printer
motor, heater or probe test.

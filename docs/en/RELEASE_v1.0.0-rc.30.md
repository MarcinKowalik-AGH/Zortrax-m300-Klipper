<!-- Marcin Kowalik <mkowalik@agh.edu.pl> | RELEASE_v1.0.0-rc.30.md - Documents filament transport settings and the Orange Pi update. -->
# M300 Classic RC30 — filament withdrawal and loading settings

Set the following four options in the existing Klipper `[m300_filament]` section. The OLED, Fluidd, OrcaSlicer and the native material commands share these settings. Temperatures use °C and filament speeds use mm/s.

```ini
unload_temperature: 240
unload_speed: 2
load_temperature: 0
load_speed: 2
```

Zero selects the saved print temperature for loading during a paused change. Standalone Load and a change with a cold saved target use 240°C by default, or the legacy `procedure_temperature` if configured. A positive value such as 210 selects a fixed loading temperature for both cases. Withdrawal completes at the configured unload target before the nozzle switches to the loading target. Feed waits for insertion confirmation and temperature readiness. Completing the procedure restores the saved print setpoint.

An explicit `TEMP` on `ZORTRAX_LOAD` or `ZORTRAX_UNLOAD` applies to that operation. On `ZORTRAX_CHANGE` it overrides only the loading target. After saving configuration, restart Klipper while idle. Check the four settings with `ZORTRAX_FILAMENT_STATUS`.

## Installation

When the printer is idle and Ready with heater targets off, update the existing `orange-pi` checkout:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

The host installer adds missing settings and preserves selected values. MCU 1.0.8 supports this release. The separate firmware archive is `M300_SD.zip`. Fluidd uses port 4480 and its separate installer accepts `--update-fluidd --port 4480`. The manual retains illustrations from beta.20.

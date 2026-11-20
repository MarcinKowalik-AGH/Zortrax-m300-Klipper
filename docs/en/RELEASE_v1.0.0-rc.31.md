<!-- Marcin Kowalik <mkowalik@agh.edu.pl> | RELEASE_v1.0.0-rc.31.md - Documents automatic and numeric material settings and the RC30 upgrade. -->
# M300 Classic RC31 — automatic and numeric filament settings

Each of the four options in the existing `[m300_filament]` section accepts `auto` or a number. The OLED, Fluidd, OrcaSlicer and paused `M600` operation share these settings.

```ini
unload_temperature: auto
unload_speed: auto
load_temperature: auto
load_speed: auto
```

Automatic material transport uses 240°C for both withdrawal and loading. Both directions retain the previous 2 mm/s filament speed. During a 210°C print, an automatic change performs both phases at 240°C and restores the 210°C print target after completion. Insertion confirmation and print resume remain explicit operator actions.

To change just one setting, enter a number such as `unload_speed: 3` and leave the other options on `auto`. A command with an optional material `TEMP` parameter also accepts `TEMP=auto` for a one-time 240°C target. On `ZORTRAX_CHANGE` this parameter controls loading.

## Orange Pi update

Finish the print, wait for Ready with the heater targets off, and run these commands in the existing `orange-pi` checkout:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

The installer converts the RC30 stock profile to four automatic settings, preserves custom numeric values and migrates the old load-temperature zero to `auto`. After editing the configuration manually, restart Klipper while idle. `ZORTRAX_FILAMENT_STATUS` reports the selected modes in `configured_material` and the effective numeric settings alongside it.

The host supports MCU 1.0.8. `M300_SD.zip` is the separate firmware archive. Fluidd uses port 4480. Its separate installer accepts `--update-fluidd --port 4480`. The manual retains illustrations from beta.20.

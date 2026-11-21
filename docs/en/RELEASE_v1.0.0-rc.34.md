<!-- Marcin Kowalik <mkowalik@agh.edu.pl> | RELEASE_v1.0.0-rc.34.md - Documents M300 macro names and configuration migration. -->
# M300 macro names · RC34

The 36 printer-specific operator macros now use the `M300_` prefix, including `M300_STATUS`, `M300_LOAD`, `M300_UNLOAD` and `M300_MAIN_MENU`. The OLED and Fluidd call the same procedures. Existing G-code files can call the old names. Klipper commands including `START_PRINT`, `END_PRINT`, `PAUSE`, `RESUME` and `BED_MESH` keep their names. Direct service commands such as `ZORTRAX_MCU_STATUS` remain available. [Macro catalogue](../pl/MACRO_REFERENCE.md).

## Orange Pi update

Finish the print, turn off the heaters and wait for Ready. In the existing `orange-pi` checkout run:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py &&
python3 M300_HOST/setup_fluidd.py --apply
```

The installer updates the host. RC34 supports MCU 1.0.8. The separate MCU archive is `M300_SD.zip`. Fluidd runs on port 4480. Its optional installer accepts `--update-fluidd --port 4480`. The manual retains historical illustrations from beta.20.

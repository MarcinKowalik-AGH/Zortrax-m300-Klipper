# Zortrax M300 Classic — Klipper port

[Polski](README_PL.md) · [Build](docs/en/BUILD.md) · [Install](docs/en/INSTALL.md) · [Current limits](docs/en/STATUS.md)

Source repository for **M300 Classic**, STM32F103 at 72 MHz, Cartesian mechanics.
Current snapshot: **MCU R14.5 + native host R15.7** on pinned Klipper
`ee2c6fb6b00b2b5d097ef70d0868df7d74943b51`.

GitHub Actions performs a clean GNU ARM build, host/register-model tests,
and nine real Klippy FILEOUTPUT processes. The downloadable artifact contains:

- Compiled BIN, ELF, dictionary, map, build configuration and provenance.
- Validated `M300APP.M3B` and an SD ZIP containing that application.
- The matching Orange Pi **host R15.7 update**, with tests and exact rollback.
- A complete host source snapshot, validation reports and checksums.

A push to main changing source or CI starts the workflow. It can also be started
with **Actions → Build M300 STM32F103 and host R15.7 → Run workflow**.
Open the completed run and download `m300-r14_5-host-r15_7-<commit>` under Artifacts.

| Directory | Purpose |
|---|---|
| mcu/SOURCE_MCU | MCU overlay, verified upstream patcher and ARM builder |
| mcu/tests | Guard snapshot and native heater-check replay |
| host/klippy/extras | Canonical M300 host modules and resources |
| host/update_template | Installer and self-contained regression fixtures |
| host/config | Display-only settings |
| ci | Staging, validation and release packaging |
| tests/fixtures | Synthetic configurations for FILEOUTPUT only |
| docs/en, docs/pl | Separated English and Polish documentation |

Host files have one canonical runtime source. CI assembles the installable
update from those files; it does not rely on manually maintained ZIP snapshots.
Upstream is downloaded at the fixed commit and checked against its recorded
SHA-256 before patching. Source changes never fetch an unpinned Klipper main.

R15.6 restores native menu controls and recognized split-homing actions, fixes
initial contrast, and adds the original moon with **Entering sleep mode**:
after five idle minutes, ten seconds of acknowledged notice, then display off.
During work the display only dims. First invisible knob input wakes without
selecting a hidden action. Printer heater, motion and idle_timeout settings
remain under their existing owners.

R15.7 adds factory hardware identification and automatic Z=400/800 selection,
shared with M07 and OLED status. It requires the matching R14.5 MCU application.
See [Hardware variants](docs/en/HARDWARE_VARIANTS.md).
No bootloader or factory firmware dump is distributed. CI runs no flash,
serial, physical movement or heating operation. Physical Z scale/range and
other remaining qualifications are recorded in STATUS.md.

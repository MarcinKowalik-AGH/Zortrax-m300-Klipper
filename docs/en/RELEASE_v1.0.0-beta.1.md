First versioned beta of the **classic Zortrax M300 Klipper integration**.
MCU R14.18, host R16.12 / print controller 0.13.16.29 and precompiled Fluidd
1.37.7. This release is for the STM32F103 Classic; not Plus, Dual or Inventure.
An already installed compatible M300 SD bootloader is required.

## Downloads and first installation

- **Zortrax_M300_Klipper_v1.0.0-beta.1.zip**: complete matching MCU, pinned
  Klipper host source, precompiled Fluidd, first-install/update helpers,
  configuration, build provenance, licenses and validation reports.
- **FIRST_INSTALL_EN.md / FIRST_INSTALL_PL.md**: steps from a blank Raspberry Pi
  or Orange Pi, including OS, UART, KIAUH, SD application flashing and checks.
- **SHA256SUMS-v1.0.0-beta.1.txt**: hashes for the downloadable ZIP and guides.

Read the [English first-install guide](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-beta.1/docs/en/FIRST_INSTALL.md)
or [instrukcja instalacji po polsku](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-beta.1/docs/pl/FIRST_INSTALL.md).
KIAUH prepares services; our fresh installer installs the actual M300 runtime.
There is no universal Raspberry/Orange Pi disk image. MCU and Fluidd are ready
to use; the host's small C helper builds locally for the target CPU.

## Included behavior

- Native Cartesian motion and gated hardware X/Y STEP timers, original OLED
  and encoder, sleep/wake and contextual animated procedure screens.
- Native M300 contact homing, OEM five-point mechanical leveling, plus separate
  native Bed Mesh compensation over five conductive pads with 25 measurements.
- Shared G-code/Z-code Start/End, concurrent heating, optional platform soak,
  automatic saved-mesh selection and guarded X300 Y305 parking.
- Native protected pause/resume and M600, bed temperature hold, nozzle standby
  after 600 seconds/off after 1800 seconds, explicit material confirmation.
- Maintenance/Settings/Models/Information/Help menu, 16-level brightness,
  Heat the platform, Full platform preheating and semantic OLED graphics.
- Shared errors and status LEDs, MCU-local cooling with 50°C ON / 45°C OFF,
  factory hardware/Z-scale selection and factory identity readout.
- Whole-file validation of the explicit Classic M300 Z-code subset; unsupported
  files fail before execution. Read-only `check-zcode.py` is included.

## Validation and beta scope

The attached reports identify the exact source and compiled MCU dictionary.
CI runs 637 host regressions, installer/rollback tests, actual pinned Klippy
FILEOUTPUT workflows, the actual first-install configuration, native register
models, the STM32 ARM build and Fluidd tests/build. The published assets are
downloaded from that successful build, not rebuilt after tagging.

Physical evidence includes an HW05 dry run at 750000 baud with segmented
400 mm/s commands and zero retransmitted/invalid bytes in its 201.6-second
sample. The supplied default motion profile remains 300 mm/s. This does not
qualify loaded printing at 400 mm/s, every SBC/hardware revision, or all
Z-Suite exports. Initial PID, extrusion and travel values must be checked on
the installed printer; individual pad boundaries require measurement.

The beta tag and assets are immutable. Later development is on main with
ready update files on orange-pi. Generic upstream Klipper/Fluidd updates do
not preserve this port. No private factory dump or bootloader is included.

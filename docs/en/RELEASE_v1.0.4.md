# M300 Classic 1.0.4 — OLED fixes, optional camera and thermal graphs

26 November 2026. **Host 1.0.4 / R16.19, MCU 1.0.9**. Supersedes the immutable
1.0.3 release. This full ZIP collects the fixes previously deployed through
`orange-pi`, together with current installers, instructions and the new operator
screenshot. It applies to M300 Classic with the original STM32F103 controller.

## Changes since the 1.0.3 release snapshot

- Optional USB camera with its own `m300_camera.conf`, explicit enable/disable,
  built Fluidd integration and UV4L-MJPEG support for the tested OrcaSlicer 2.5.2.
- Independent optional **Host** and **MCU** graph curves. Both includes start
  disabled in `printer.cfg`; commenting an include disables its option. Other
  Orange Pi zones are read on demand by `read-host-temperatures.py`.
- MCU 1.0.9 provides internal ADC16 temperature telemetry. The graph and
  `M300_MCU_TEMPERATURE` share the same approximate die measurement.
- Recognized missing or unstable nozzle contact lowers the bed by up to
  100 mm inside known Z travel, invalidates Z and asks for cleaning. Unknown Z
  does not authorize a blind retreat. Real MCU and thermal faults retain shutdown.
- A successful verified Z home resolves its preceding contact notice and lighting
  indication without clearing unrelated errors.
- Native extruder `check_gain_time: 40` addresses the observed delayed warm-reheat
  response. Existing custom sections are preserved. Heating gain, cumulative
  error limits, ADC, PID and independent MCU protection remain active.
- Automatic mesh-observer navigation no longer takes over Tune during an active
  or paused print. `START_PRINT ... MESH=AUTO` still loads a saved profile.
- Fan test retains presentation ownership while switching fans; late completion
  reports and status requests cannot silently end its screen. Long-press Back,
  Current procedure, terminal return paths and shared PID macros were corrected.
- New-host installation supports Python 3.10–3.13, including Debian 13 Trixie.
  Both the full ZIP and Git checkout contain the diagnostic modules and templates.

The package also retains the planned-restart heartbeat, mesh-cancel and runtime
counter fixes. Existing PID, mesh, qualified Z, UART and optional configuration
choices are preserved by the updater.

## Install or update

For a new host use [FIRST_INSTALL](FIRST_INSTALL.md). The public release includes
`Zortrax_M300_Klipper_v1.0.4.zip`, its external SHA-256 file and separate PL/EN
first-install guides. The ZIP contains the complete patched Klipper runtime,
MCU SD image, built Fluidd, configuration, installers and reports.

For an existing idle, Ready printer with heater targets off:

```bash
cd "$HOME/m300-orange-pi" &&
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

Update the web interface separately with
`python3 install-orange-pi.py --update-fluidd --port 4480` and reload Fluidd.
MCU **1.0.9 needs no reflash**. Upgrade an older MCU before enabling its internal
temperature option. [MCU instructions](MCU_FIRMWARE_1.0.9.md).

## Verification and hardware scope

The software suite includes 1055 host tests, actual Klippy FILEOUTPUT,
upgrade/rollback, complete first installation on Python 3.12 and 3.13 and frontend
tests. The [OLED audit](OLED_MENU_AUDIT.md) covers 44 views, 582 rows and 26 command
bindings. These tests do not actuate a physical printer.

The new screenshot confirms visible camera and Host/MCU graph UI on the operator's
printer. It is not a blanket acceptance of every procedure or sensor accuracy.
The [hardware register](../pl/ACCEPTANCE_REGISTER.md) retains reported failures
and pending tests. The illustrated OLED atlas keeps its historical **beta.20**
baseline. Existing 1.0.3 assets and tag remain unchanged.

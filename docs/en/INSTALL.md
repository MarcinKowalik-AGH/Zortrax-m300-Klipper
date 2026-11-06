# Install the main Orange Pi release

[Procedure bindings](MAINTENANCE_MATERIAL.md) · [Validation and printer tests](PRINT_CONTEXT.md)

The main package pairs the native R16.12 host with MCU R14.16 for M300 Classic.
The host installer also accepts supported installations running earlier MCU revisions.
Use the same UART rate on the MCU and the Orange Pi. The R14.14 dry-run
baseline uses 750,000 baud. The installer preserves the configured baud.
Factory serial and OEM print time require R14.6 or later.
OLED hold-to-move with local button release stop requires R14.7.
It accepts recognized baselines from R15.3 through the initial R16.12 build,
including the browser modules from the M300 TEST01 v0.13.2 R2 install archive.
The installer checks the existing module hashes before it writes anything.

## Install directly from Git on Orange Pi

GitHub Actions builds and verifies the host, Fluidd and MCU. The same run
publishes a compact checkout with the ready-to-install files. Run this on the
Orange Pi as the Klipper user while the printer is idle:

```bash
m300_dir="$HOME/m300-orange-pi"
if [ -d "$m300_dir/.git" ]; then
  git -C "$m300_dir" pull --ff-only
else
  git clone --depth 1 --single-branch --no-tags --branch orange-pi \
    https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper.git "$m300_dir"
fi &&
python3 "$m300_dir/install-orange-pi.py"
```

The full build archive and test reports are also available in the successful
[GitHub Actions run](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/actions/workflows/build-m300.yml).

The installer checks the delivered file hashes, reads the active Klipper paths
from Moonraker, updates the host and macro groups, and deploys the compiled
Fluidd to the existing nginx web root on port 4080. It saves the old web files
and preserves config.json. A host already on the same R16.12 files skips its
restart. For a different nginx port, pass `--port`; for an atypical nginx
configuration, pass `--fluidd-root /absolute/path/to/current/fluidd`.

Pad mesh revision `0.13.16.18-PAD-OLED` updates the host and compiled Fluidd.
One `ZORTRAX_BED_MESH` now prepares both heaters and required native homing
before measurement. The nozzle uses 180 °C as a minimum and preserves a
hotter working temperature. Tune displays preparation and point progress,
acceptance or a detailed rejection. The OLED opens the animated five-pad page
for the same run and restores its previous screen after success. The parameter
form exposes every field; use its Send button to submit overrides. This update
also establishes shared 5 mm Z clearance before XY in native homing, OEM
leveling and pad mesh. Successful pad mesh restores prior heater targets
(off stays off); failure turns both targets off. No additional MCU flash is
required.
Fully reload Fluidd after installation to load the new web files.

Revision `0.13.16.19-PAD-ZERO-MARGIN` permits both `edge_margin: 0` and
`travel_margin: 0`, preserving native X0/Y0 when a physical pad extends
beyond the travel limits. Explicit pad dimensions are retained by the installer.
The usual installer can also repair the preceding adapter's known pad-geometry
startup error without requiring unavailable `print_stats`. Other startup errors,
runtime shutdowns, printing and paused states remain refused. The updated host
must reach Ready before Fluidd deployment continues. Review the corrected
[home-inside-metal geometry](LEVELING.md#home-can-lie-inside-the-physical-metal)
before another measurement.

Expect `INSTALLED_M300_R16_12_FULL`, then reload Fluidd. Keep the host receipt
and the reported Fluidd backup path. The installer does not run printer
movement, heating or MCU flashing.

## Read-only checks and first tests

In the Fluidd console run:

```gcode
STATUS
ZORTRAX_HARDWARE_STATUS
ZORTRAX_MOTION_STATUS
ZORTRAX_CALIBRATION_STATUS
ZORTRAX_FILAMENT_STATUS
ZORTRAX_LINK_STATUS
ZORTRAX_UI_STATUS
ZORTRAX_FANS_STATUS
ZORTRAX_MAINTENANCE_STATUS
ZORTRAX_PROCEDURE_STATUS
ZORTRAX_SETTINGS_STATUS
ZORTRAX_INFO REFRESH=0
QUERY_PROBE
```

Confirm Ready, the real HW05/Z400 identity, normal native control, host R16.12,
fan/maintenance/procedure revisions and an open PC7 contact with clearance.
Motion reports the native rail speeds and a fault phase. Calibration still
reports its four independent movement speeds. The packaged
[M300 Fluidd build](FLUIDD_M300.md) renders the SVG in the same results dialog.
The link lifecycle revision remains 0.13.16.2-LIFECYCLE-RECONNECT; this is normal.
Targets are calibration/Heat 260°C, Load/Unload 240°C and ordinary Z home at
least 180°C. A hotter pre-existing target during ordinary homing is retained.

Follow the supervised sequence in [the validation report](PRINT_CONTEXT.md).

For a read-only SD import check on a printer with a qualified SD configuration,
run `ZORTRAX_SD_STATUS`, browse to a small G-code file under **Models**, and
open its preview. Check that the model becomes ready to start and cancel the
preview. Repeat with a larger file and check that the byte count reaches its
file size. The import finishes before the print can start.
The first procedure checks are Heat and bounded platform movement, then
Load/Unload, the interactive Fan test, ordinary Z reference and Autocalibration. Change requires an
already paused native print. Do not treat generic PROBE_ACCURACY as the OEM
wizard or a substitute for its owned measurement frame and release checks.

## Models from SD

Follow the [Models procedure](MODELS_SD.md) to enable the existing SD option
and test listing and import before starting a print. `ZORTRAX_MODELS_STATUS`
reports the current import and selection.

## Contextual print controls

Use [Print contexts](PRINT_CONTEXT.md) for the OLED 10-second holds,
Pause menu and Fluidd exact reprint. Re-run
`python3 setup_fluidd.py --apply` to group the ZORTRAX_REPRINT macro.

## Rollback and MCU

For a host rollback, stop Klipper, enter the included
`M300_HOST_R16_12_NORMAL_UI` directory, run
`python3 install.py --rollback /EXACT/PATH/RECEIPT.json`, then start Klipper.
The receipt restores exact prior host/config bytes and protects later edits.
For the frontend, restore the saved web directory to the reported
`fluidd_root` and reload nginx.

The included `MCU/M300APP.M3B` and `MCU/M300_R14_16_SD.zip` contain the
compiled M300 Classic application for the existing M300 SD/bootloader procedure.
The application starts at 0x08008000. Flashing is a separate operation.
BUILD_PROVENANCE.json identifies the tested source. A printer already running
the hardware-tested R14.14 candidate can receive the host and Fluidd update
before its next scheduled MCU flash. The full Actions artifact
also contains the HOST_SOURCE snapshot.

The R14.15 waiting/disconnection animation runs locally on the MCU and therefore
appears only after the new MCU image is flashed using the existing SD procedure.
Updating the Orange Pi host alone does not install these local MCU graphics.
The X/Y STEP timer core and UART rate are unchanged from R14.14.

R14.16 and the current host use the same temperature-only upper-fan thermostat:
50 C ON / 45 C OFF. A heater target no longer starts cold automatic cooling.
The MCU ADC1-stale handoff fix needs the new MCU image as well as the host
update. See [cooling behavior and acceptance](COOLING.md). Check
`ZORTRAX_FANS_STATUS` for `fan_revision: 0.13.16.14-THERMOSTAT-50-45` and
`ZORTRAX_MCU_STATUS` for `mcu_release: 0.13.14.16-THERMOSTAT-50-45-UART8`.

The 0.13.16.12 host menu update restores the preceding OLED page after an
externally started procedure, including native Klipper status after Fluidd
homing. Check `ZORTRAX_MENU_STATUS` for
`menu_revision: 0.13.16.13-BRIGHTNESS-MESH-BOUNDS`. This update also synchronizes
the OLED/Fluidd brightness bars, preserves Back after saving and reports pad
geometry against the current XY limits in `ZORTRAX_BED_MESH PREVIEW=1`. It
does not require another MCU flash when R14.15 is already installed.

The pad mesh adapter uses configured physical pad dimensions and fits their reachable
corners to existing XY limits, including X300/Y305. `ZORTRAX_BED_MESH PREVIEW=1`
reports the actual plan and every adjusted corner. The macro now inherits
`[m300_pad_mesh]` settings. `ZORTRAX_PAD_MESH_STATUS` reports
`revision: 0.13.16.15-PAD-TRAVEL`. This is a host-only update; MCU R14.16
and thermal behavior remain unchanged.

### OLED RLE benchmark

Run these commands in Fluidd with R14.8 or later running and the printer idle.

```text
ZORTRAX_OLED_RLE_BENCH LENGTH=32 OFFSET=1
ZORTRAX_OLED_RLE_BENCH LENGTH=128 OFFSET=1
```

The console reports MCU cycles for the previous C fill and the new Thumb-2
fill. Each result is the minimum of five samples with interrupts enabled.
Offset 1 models one alignment of the DMA slot. The test writes to a scratch
buffer in SRAM. The numbers measure fill time only. `ZORTRAX_OLED_STATUS`
reports complete frame timings, which also include the host and serial link.

# Optional host temperature

Fluidd can show independent optional **Host** (CPU) and **MCU** (STM32) curves.
Other Orange Pi thermal readings remain available on demand over SSH. Both
includes are commented out by default.

## Existing installation

From the `orange-pi` checkout, download and copy the template if not yet installed:

```bash
cd "$HOME/m300-orange-pi" &&
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
cp -n FIRST_INSTALL/m300_host_temperature.cfg "$HOME/printer_data/config/"
```

This option does not require running `install-orange-pi.py`.
Fresh installations copy the template with its include commented out.
Enable it in `printer.cfg`, before `SAVE_CONFIG`:

```ini
[include m300_host_temperature.cfg]
```

Disable it by commenting out that line:

```ini
# [include m300_host_temperature.cfg]
```

After changing the include, run `FIRMWARE_RESTART` in Fluidd while the printer
is idle. The configuration defines a read-only temperature sensor.

## Other readings

Run over SSH:

```bash
python3 "$HOME/m300-orange-pi/read-host-temperatures.py"
```

Use `--json` for structured output. This only reads Linux system files; it works
with the include disabled and does not restart services or record history.

On the observed Orange Pi Zero 4 / A733, zones 0–4 are respectively
`cpub_thermal_zone`, `ddr_thermal_zone`, `npu_thermal_zone`, `cpul_thermal_zone`,
and `gpu_thermal_zone`. Only zone 0 is registered in Klipper as **Host**.
On other boards or after changes to thermal zone numbering, identify the CPU
zone with the command and adjust `sensor_path` before enabling the include.
The file must exist and be readable by the Klipper account.

## Optional STM32 temperature diagnostics

MCU 1.0.9 provides `M300_MCU_TEMPERATURE_ABI=1` and a long ADC16 sample time.
The optional `m300_mcu_temperature.py` reads the internal sensor every 5 seconds
through the native ADC queue without enabling debug memory reads. It registers
no heater. When its include is enabled, it exposes `temperature_sensor MCU`
for Fluidd using the existing reading, without another ADC acquisition.

Install [MCU 1.0.9](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/main/docs/en/MCU_FIRMWARE_1.0.9.md) first. On an idle printer, from the
updated `orange-pi` checkout:

```bash
python3 install-orange-pi.py &&
cp -n FIRST_INSTALL/m300_mcu_temperature.cfg "$HOME/printer_data/config/"
```

Add `[include m300_mcu_temperature.cfg]` to `printer.cfg` above `SAVE_CONFIG`.
The installer performs the full process restart required by Python addon changes.
After saving the include and reconnecting Fluidd, run `FIRMWARE_RESTART` in its console to
start a new MCU session. Wait for Ready and about 5 seconds for a sample, then run
`M300_MCU_TEMPERATURE` to read the diagnostic. The same object is available at
`http://127.0.0.1:7125/printer/objects/query?m300_mcu_temperature`.

The temperature is the die temperature, using nominal STM32F103 conversion
parameters. It is approximate; `adc_voltage` and `temperature_offset` allow
adjustment. ADC fractions/raw readings and sample age are reported as well.
Stale, disconnected or shutdown measurements return a null temperature.
To disable, comment out the include and run `FIRMWARE_RESTART`. Disable this
include before reverting to MCU 1.0.8; the addon rejects that older capability.

## Independent includes in printer.cfg

Enable either or both options by uncommenting their main-config includes:

```ini
[include m300_host_temperature.cfg]
[include m300_mcu_temperature.cfg]
```

Disable an option by commenting out its include, then run `FIRMWARE_RESTART`.
A disabled include loads neither its file nor its sensor; it does not require
that hardware capability. Klipper can therefore start with MCU diagnostics
disabled on older firmware, or with both optional files absent.
The MCU graph is enabled by default when the MCU include is active.
Use `show_on_graph: False` inside its separate config only for diagnostic-only
operation. Stale or invalid readings produce missing graph data, not an old value.

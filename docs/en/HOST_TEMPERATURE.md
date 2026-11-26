# Optional host temperature

Fluidd gets one additional temperature series, **Host**, for the host CPU.
Other Linux thermal readings are available on demand over SSH, without adding
graph series. This feature is disabled by default.

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
no heater and no additional graph series.

Install [MCU 1.0.9](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/main/docs/en/MCU_FIRMWARE_1.0.9.md) first. On an idle printer, from the
updated `orange-pi` checkout:

```bash
cp M300_HOST/payload/m300_mcu_temperature.py "$HOME/klipper/klippy/extras/" &&
cp M300_HOST/payload/m300_resources.py "$HOME/klipper/klippy/extras/" &&
cp -n FIRST_INSTALL/m300_mcu_temperature.cfg "$HOME/printer_data/config/"
```

Add `[include m300_mcu_temperature.cfg]` to `printer.cfg` above `SAVE_CONFIG`.
Replacing Python addons requires a full Klipper process restart. Over SSH run:

```bash
sudo systemctl restart klipper.service
```

When Fluidd reconnects to the host, run `FIRMWARE_RESTART` in its console to
start a new MCU session. Wait for Ready and about 5 seconds for a sample, then run
`M300_MCU_TEMPERATURE` to read the diagnostic. The same object is available at
`http://127.0.0.1:7125/printer/objects/query?m300_mcu_temperature`.

The temperature is the die temperature, using nominal STM32F103 conversion
parameters. It is approximate; `adc_voltage` and `temperature_offset` allow
adjustment. ADC fractions/raw readings and sample age are reported as well.
Stale, disconnected or shutdown measurements return a null temperature.
To disable, comment out the include and run `FIRMWARE_RESTART`. Disable this
include before reverting to MCU 1.0.8; the addon rejects that older capability.

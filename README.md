# M300 Classic v1.0.3 — Orange Pi

This checkout contains the tested host, prebuilt Fluidd and MCU image.
The matching SD application is `MCU/M300APP.M3B` (MCU 1.0.9). Install it through your existing M300 bootloader.
For a NEW KIAUH host (including Debian 13 / Python 3.13), run `python3 install-new-host.py --serial /dev/ttyS2 --baud 750000 --apply`.
Substitute the actual enabled UART and bootloader baud for your board. No previous Pi or personal configuration archive is needed.
Run `python3 install-orange-pi.py` as the Klipper user while idle and Ready to update the host.
For an explicit Fluidd repair on port 4480, run `python3 install-orange-pi.py --update-fluidd --port 4480`.
The updater preserves qualified Z, mesh and PID. Host print-time accounting works on compatible older MCU firmware.
With MCU 1.0.8 or newer, Klipper automatically synchronizes print time to the board while idle. Install the MCU image from SD only if the board still requires the firmware update.

Optional USB camera (disabled by default): `python3 install-camera.py --enable --apply`. Edit `~/printer_data/config/m300_camera.conf` and run `python3 install-camera.py --apply` to change it or disable streaming. See CAMERA_PL.md / CAMERA_EN.md.

Optional host CPU temperature: one Host graph series, enabled with `[include m300_host_temperature.cfg]`. Other readings: `python3 read-host-temperatures.py`. See HOST_TEMPERATURE_PL.md / HOST_TEMPERATURE_EN.md.

The new-host installer copies both optional temperature configs, disabled by default. Enable STM32 diagnostics with `[include m300_mcu_temperature.cfg]` (MCU 1.0.9 or newer), run `FIRMWARE_RESTART`, then `M300_MCU_TEMPERATURE`. The MCU include adds a read-only MCU graph curve using the existing ADC. Comment either temperature include in printer.cfg to disable that option.

Contact recovery lowers the bed by 100 mm within the Z travel after a recognized nozzle-contact failure, invalidates Z and asks for cleaning. MCU shutdown guards remain active. See CONTACT_RECOVERY_PL.md / CONTACT_RECOVERY_EN.md for the existing-host update.

[Update instructions](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/234c3c896033e96bff238d38974be589090eb4ef/docs/en/INSTALL.md)

Source commit: `234c3c896033e96bff238d38974be589090eb4ef`

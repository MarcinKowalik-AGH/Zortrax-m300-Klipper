# M300 Classic v1.0.0-rc.10 — Orange Pi

This checkout contains the tested host, prebuilt Fluidd and MCU image.
Run `python3 install-orange-pi.py --port 4480` as the Klipper user while idle and Ready.
The updater verifies the existing Fluidd site on port 4480 and preserves its nginx configuration.
The updater preserves qualified Z, mesh and PID. Host print-time accounting works on compatible older MCU firmware.
With MCU 1.0.5, Klipper automatically synchronizes print time to the board while idle. Install the MCU image from SD only if the board still requires the firmware update.

[Update instructions](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.10/docs/en/INSTALL.md)

Source commit: `570ebc1d5c8adcc9b2a60779999421e25621a4c0`

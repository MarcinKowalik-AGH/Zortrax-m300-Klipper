# M300 Classic v1.0.0-rc.9 — Orange Pi

This checkout contains the tested host, prebuilt Fluidd and MCU image.
Run `python3 install-orange-pi.py --port 4480` as the Klipper user while idle and Ready.
The updater verifies the existing Fluidd site on port 4480 and preserves its nginx configuration.
The updater preserves qualified Z, mesh and PID. Host print-time accounting works on compatible older MCU firmware.
Install the MCU image separately from SD. After enabling MCU counter writes with the board backup, Klipper synchronizes automatically while idle.

[Update instructions](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.9/docs/en/INSTALL.md)

Source commit: `fbecbae8810aaa7f77663c8758b71b13380305b9`

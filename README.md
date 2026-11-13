# M300 Classic v1.0.0-rc.8 — Orange Pi

This checkout contains the tested host, prebuilt Fluidd and MCU image.
Run `python3 install-orange-pi.py --port 4480` as the Klipper user while idle and Ready.
The updater preserves qualified Z, mesh and PID. Host print-time accounting works on compatible older MCU firmware.
Install the MCU image separately from SD. After enabling MCU counter writes with the board backup, Klipper synchronizes automatically while idle.

Source commit: `560b2b9ac23828fa86bb1d2c4c609d3d0083e497`

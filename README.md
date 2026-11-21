# M300 Classic v1.0.0-rc.34 — Orange Pi

This checkout contains the tested host, prebuilt Fluidd and MCU image.
Run `python3 install-orange-pi.py` as the Klipper user while idle and Ready to update the host.
For an explicit Fluidd repair on port 4480, run `python3 install-orange-pi.py --update-fluidd --port 4480`.
The updater preserves qualified Z, mesh and PID. Host print-time accounting works on compatible older MCU firmware.
With MCU 1.0.8, Klipper automatically synchronizes print time to the board while idle. Install the MCU image from SD only if the board still requires the firmware update.

[Update instructions](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/38e1c70e5ed7c974c709b9923613e22994832e57/docs/en/INSTALL.md)

Source commit: `38e1c70e5ed7c974c709b9923613e22994832e57`

# M300 Classic v1.0.0-rc.7 — Orange Pi

This checkout contains the tested host, prebuilt Fluidd and MCU image.
Run `python3 install-orange-pi.py --port 4480` as the Klipper user while idle and Ready.
The updater preserves qualified Z, mesh and PID. Host print-time accounting works on compatible older MCU firmware.
The MCU image is a separate SD update. Enable MCU counter writes after qualifying the board backup.

Source commit: `604999e7b9015a5b61ce528a0725bafe2f704bcd`

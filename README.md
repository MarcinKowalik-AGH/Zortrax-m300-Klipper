# M300 Classic v1.0.3 — Orange Pi

This checkout contains the tested host, prebuilt Fluidd and MCU image.
For a NEW KIAUH host (including Debian 13 / Python 3.13), run `python3 install-new-host.py --serial /dev/ttyS2 --baud 750000 --apply`.
Substitute the actual enabled UART and bootloader baud for your board. No previous Pi or personal configuration archive is needed.
Run `python3 install-orange-pi.py` as the Klipper user while idle and Ready to update the host.
For an explicit Fluidd repair on port 4480, run `python3 install-orange-pi.py --update-fluidd --port 4480`.
The updater preserves qualified Z, mesh and PID. Host print-time accounting works on compatible older MCU firmware.
With MCU 1.0.8, Klipper automatically synchronizes print time to the board while idle. Install the MCU image from SD only if the board still requires the firmware update.

Optional USB camera (disabled by default): `python3 install-camera.py --enable --apply`. Edit `~/printer_data/config/m300_camera.conf` and run `python3 install-camera.py --apply` to change it or disable streaming. See CAMERA_PL.md / CAMERA_EN.md.

[Update instructions](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/89aede3cc176361f315a91633468a4ac400e1580/docs/en/INSTALL.md)

Source commit: `89aede3cc176361f315a91633468a4ac400e1580`

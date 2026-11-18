# M300 Classic RC19 and MCU 1.0.6

MCU 1.0.5 required the high-density STM32 identification register to return 0x414 during every factory-counter transfer. On the standalone controller this register can read zero. MCU 1.0.6 qualifies the processor, 256 KiB Flash and factory hardware record in standalone operation. The host reports the detected target and which component deferred an idle transfer. The controller still checks its serial, bank contents, movement, heater outputs and execution deadlines.

Install the host with `python3 install-orange-pi.py` in the updated Orange Pi checkout while the printer is idle and Ready. Install the application from `MCU/M300_SD.zip` using the existing SD bootloader. Keep the current print-time journal. Fluidd uses port 4480. The separate Fluidd repair command uses `--update-fluidd --port 4480`. OLED illustrations are from beta.20.

After Ready, run `ZORTRAX_HARDWARE_STATUS` and `ZORTRAX_INFO REFRESH=0`. Confirm MCU 1.0.6, a higher factory-minute value, normalized banks and cleared pending status. Repeat after a normal cold restart. Real-board acceptance is pending. [MCU installation and counter fields](MCU_FIRMWARE_1.0.6.md).

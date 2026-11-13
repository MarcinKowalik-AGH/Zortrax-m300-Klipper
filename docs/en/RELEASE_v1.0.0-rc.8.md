# M300 RC8 automatic print-time synchronization

Klipper now calls the MCU counter during normal operation. It records the time spent printing the model, including completed, cancelled and interrupted jobs, and retains it on the Orange Pi. With synchronization enabled, Klipper sends pending whole minutes when the printer is idle. The MCU checks the write conditions, reads the factory ID0 record, updates it using the two settings banks and reports the result. Klipper reads back the committed value, reconciles its journal and keeps the remaining seconds for the next transfer.

A fresh update requires at least one pending whole minute. An idle check with less time pending leaves Flash untouched.

## Update

Update the Orange Pi while the printer is idle and Ready:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Install the MCU 1.0.4 application separately from `MCU/M300_SD.zip`. Keep the verified full Flash backup for this board and its existing `factory_counter_backup:` entry under `[m300_mcu]`, or add the entry if enabling the feature for the first time. When the printer is eligible to write, synchronization runs without a restart. Earlier compatible MCU firmware still supports the host counter. Check `ZORTRAX_HARDWARE_STATUS` for synchronization and bank state, and `ZORTRAX_INFO REFRESH=0` for the factory minutes, local seconds and combined total. The beta.20 OLED illustrations remain the historical reference. [MCU update and counter checks](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.8/docs/en/MCU_FIRMWARE_1.0.4.md).

## Verification

The operator has already confirmed that the original firmware 1.3.1 starts after being flashed through the existing bootloader. RC8 needs a separate physical test of automatic ID0 synchronization and recovery from an interrupted Flash write. Klipper uses its transaction journal to resume an interrupted bank transfer. [Hardware acceptance](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.8/docs/pl/ACCEPTANCE_REGISTER.md).

# Zortrax M300 Classic — MCU firmware 1.0.0

**Scope:** the application firmware for the original STM32F103-based M300 Classic motherboard only. This is not an Orange Pi image, a Plus/Dual/Inventure image, or an MCU bootloader update. The separate MCU release remains compatible with the existing M300 host `1.0.0-rc.2`.

[Dedicated MCU firmware release](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.0) · [First-install procedure](FIRST_INSTALL.md)

## Numeric firmware identity

The compiled MCU exposes the exact numeric identifier `1.0.0` in both `M300_MCU_RELEASE` and the Klipper build dictionary `version`. The automatically generated `?-timestamp-hostname` identifier and developer suffix are removed from the visible firmware identity. The autonomous OLED release text reads `MCU: 1.0.0`. Source provenance, hashes, commit, build runner and timestamp remain in the build report, independently of the displayed version.

This image retains the R14.19 code and autonomous four-bit OLED graphics. Serial protocol, 750000-baud operation, ADC ownership, local fan thermostatic fallback, heater and motion interlocks, XY timer, MCU ABI, memory layout and STM32 application bootloader contract are unchanged. Already deployed R14.18 remains compatible with host RC2; updating firmware is optional unless you want the new autonomous OLED artwork and clean release naming.

## Download and integrity checks

Get `M300_MCU_v1.0.0_SD.zip` and `SHA256SUMS-mcu-v1.0.0.txt` from the dedicated release. In the same directory, run:

```bash
sha256sum -c SHA256SUMS-mcu-v1.0.0.txt
unzip -l M300_MCU_v1.0.0_SD.zip
```

The archive contains **only `M300APP.M3B`**. Its application starts at `0x08008000`. It does not replace the bootloader, factory data or any other full-flash region. The build report documents actual vector and binary-boundary checks.

## Install on an already configured printer

1. Finish the current print, ensure no print is paused, switch off heater targets, let the hotend cool and back up the printer configuration and known-good MCU application.
2. Extract the archive and copy `M300APP.M3B` alone to the root of the memory card accepted by your installed M300 application-update bootloader.
3. Stop Klipper on the Orange Pi with `sudo systemctl stop klipper`. Use the **previously validated SD application update procedure** in your existing bootloader. Do not erase all MCU flash, overwrite the bootloader or alter the factory NVM.
4. Once programming is confirmed complete, remove the firmware update file or the update card before subsequent boots. Restart the host with `sudo systemctl start klipper`.
5. Check `ZORTRAX_MCU_STATUS`, `ZORTRAX_OLED_STATUS` and `ZORTRAX_SETTINGS_STATUS` in Fluidd. Expected outcomes are model `M300_CLASSIC`, ABI 1, MCU release `1.0.0`, no MCU fault, healthy fan behavior and the existing UART speed. The operator's verified UART setting is **750000**, and this firmware does not change it.

A successful CI build is not a physical-printer acceptance test. Before any printing, verify communication, temperature readings, local cooling and endstop/contact input diagnostics. If the host cannot reach Ready, stop its service and use the previously validated procedure to restore the earlier application firmware. Do not bypass MCU safety interlocks to proceed.

## Version policy

The new MCU artifact uses its own tag `mcu-v1.0.0`. The pinned host RC2, the upstream Klipper commit and the MCU protocol ABI remain independently versioned. No general-purpose Klipper update is bundled into the firmware-only ZIP.

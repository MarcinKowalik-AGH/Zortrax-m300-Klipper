# Zortrax M300 Dual — hardware photographs (2026-11-09)

Photos of the **M300 Dual STM32 controller board** and the **Allwinner A33 / A33-Core3 Android display board**, contributed by Marcin Kowalik for the [zmxxxp-re](https://github.com/zharijs/zmxxxp-re) hardware research archive.

![Photo overview](contact_sheet.png)

## Hardware overview

- Motion controller: STM32F2xx (SWD Device ID `0x411`), factory RDP Level 1 readout protection on the tested board.
- Android board: Zortrax Rev. 2.1, Allwinner A33 / A33-Core3; Toshiba eMMC; `J5 UART0`, `P3` Android-to-MCU connector.
- Associated I/O, USB and power interface boards were also photographed.

## Photo files

The [21-photo compact PNG ZIP](M300_Dual_Photos_21_PNG_GitHub_compact.zip) (7.2 MB) is published in this repository and has been verified by SHA-256. These are reduced-resolution PNGs (maximum dimension 950 px), converted without EXIF metadata. Two later batches of additional photos are **not included yet**; contact [@MarcinKowalik-AGH](https://github.com/MarcinKowalik-AGH) for the high-resolution originals.

## Research question

The contributor is working on a Klipper port for the M300 Dual, building on detailed reverse engineering of the Inventure stock firmware (motion, thermal control and endstops). A **full original A33 eMMC image from an M200 Plus / M300 Plus / M300 Dual** would help research the stock `update.zar2` updater without erasing the protected STM32 firmware.

This directory does not host proprietary firmware images or extracted cryptographic keys.

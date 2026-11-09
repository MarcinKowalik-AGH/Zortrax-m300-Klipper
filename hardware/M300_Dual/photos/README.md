# Zortrax M300 Dual — board photographs (2026-11-09)

These photographs were supplied by Marcin Kowalik for hardware reverse engineering and documentation, particularly the [zmxxxp-re project](https://github.com/zharijs/zmxxxp-re).

![Contact sheet of the M300 Dual PCB photographs](contact_sheet.png)

## Equipment

- Zortrax M300 Dual motion-control board, STM32F2 device identified by SWD (Device ID `0x411`); stock firmware has RDP Level 1 readout protection.
- Android/display board: Zortrax Rev. 2.1, Allwinner A33 on A33-Core3, Toshiba eMMC; J5 `UART0`, P3 Android ↔ MCU connector.
- The photographs show both boards, chips, diagnostic and peripheral connectors.

## Archive

An **initial set of 21 full-resolution photos** was converted to PNG without embedded EXIF/GPS data. The complete archive is [here on Google Drive](https://drive.google.com/file/d/17nQiCtgnXpeYu5w7qF6PfHX_iuov022_/view) (access might need to be requested).

This GitHub directory currently contains the public contact sheet, which gives a quick view of the available hardware photos. The separately provided follow-up series of images is **not yet included** in the archived ZIP.

For additional photographs or original-resolution files, please contact [@MarcinKowalik-AGH](https://github.com/MarcinKowalik-AGH).

## Context / collaboration

I am developing a Klipper port for the M300 Dual, building on extensive firmware research of the Zortrax Inventure (motion, thermal control, endstops). The Dual STM32 is protected at RDP Level 1, so I am looking for a **stock eMMC dump of the Android A33 from any M200 Plus, M300 Plus, or M300 Dual** to investigate the stock firmware updater and `update.zar2` format without altering the protected controller.

This directory does not contain proprietary firmware, binary dumps or cryptographic key material.

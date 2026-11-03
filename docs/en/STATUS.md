# Current status — R16.9 test release

The Models menu opens the configured physical MCU SD reader, browses FAT16
or FAT32 folders, and imports G-code and the audited M300 Z-code subset.
The operator starts the ready local copy through native Klippy. R16.9
includes the English Settings and Information menus from R16.8.

The supported combination is MCU R14.5 and host R16.9. Software validation
covers 299 host tests, 9 repository contracts, 16 native Klippy FILEOUTPUT
cases and 28 MCU SD model scenarios. Real card and printer acceptance is
pending.

[Models from SD](MODELS_SD.md) · [Validation](VALIDATION_R16_9.md) · [Install](INSTALL.md)

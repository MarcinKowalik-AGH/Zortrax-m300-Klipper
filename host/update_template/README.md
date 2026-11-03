# M300 host R16.9

English test update for an installed native M300 Classic host with MCU R14.5.
R16.9 adds Models browsing and printing from the M300 MCU SD slot.
Select a G-code or supported Classic M300 Z-code model, wait for the checked
local copy, then choose Start printing. The existing SD opt-in is documented
in [Models from SD](docs/en/MODELS_SD.md).

Run `python3 VERIFY.py`, the 299 self-contained tests and `install.py` to
inspect the plan. Stop Klipper before applying, then start it and update the
Fluidd groups with `python3 setup_fluidd.py --apply`. Keep the rollback
receipt.

[Install on Orange Pi](docs/en/INSTALL.md) ·
[Settings and Information](docs/en/SETTINGS_INFORMATION.md) ·
[Maintenance and Material](docs/en/MAINTENANCE_MATERIAL.md) ·
[Validation](docs/en/VALIDATION_R16_9.md)

# M300 host R16.8

English test update for an installed native M300 Classic host with MCU R14.5.
R16.8 adds Settings and Information to the OLED and Fluidd, fixes Models
browsing and preview, and connects the Sleep mode toggle to the existing
display policy. Help directs operators to the project GitHub repository.

Run `python3 VERIFY.py`, the 289 self-contained tests and `install.py` to
inspect the plan. Stop Klipper before applying, then start it and update the
Fluidd groups with `python3 setup_fluidd.py --apply`. Keep the rollback
receipt.

[Install on Orange Pi](docs/en/INSTALL.md) ·
[Settings and Information](docs/en/SETTINGS_INFORMATION.md) ·
[Maintenance and Material](docs/en/MAINTENANCE_MATERIAL.md) ·
[Validation](docs/en/VALIDATION_R16_8.md)

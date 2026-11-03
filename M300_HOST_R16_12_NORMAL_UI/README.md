# M300 host R16.12

English test update for an installed native M300 Classic host with MCU R14.5 or R14.6.
R16.10 adds contextual OLED printing, pause and completion screens.
Hold the knob for 10 seconds to pause or reprint an eligible completed copy.
The pause menu uses the existing native controls and material change procedure.
[Print contexts](docs/en/PRINT_CONTEXT.md) · [Procedure inventory](docs/en/PROCEDURE_INVENTORY.md)

Run `python3 VERIFY.py`, the 341 self-contained tests and `install.py` to
inspect the plan. Stop Klipper before applying, then start it and update the
Fluidd groups with `python3 setup_fluidd.py --apply`. Keep the rollback
receipt.

[Install on Orange Pi](docs/en/INSTALL.md) ·
[Settings and Information](docs/en/SETTINGS_INFORMATION.md) ·
[Maintenance and Material](docs/en/MAINTENANCE_MATERIAL.md) ·
[Validation](docs/en/PRINT_CONTEXT.md)

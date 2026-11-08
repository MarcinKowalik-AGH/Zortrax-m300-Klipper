# M300 host R16.12

Native print controller `0.13.16.29`: shared Start/End, X300 Y305 pause park,
bed hold, 600 s nozzle standby / 1800 s nozzle OFF and confirmed M600.
See [workflow and audit](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/main/docs/pl/PRINT_CONTROL.md). MCU flashing is not required.

English test update for an installed native M300 Classic host with MCU R14.5 or R14.6.
R16.10 adds contextual OLED printing, pause and completion screens.
Hold the knob for 10 seconds to pause or reprint an eligible completed copy.
The pause menu uses the existing native controls and material change procedure.
[Print contexts](docs/en/PRINT_CONTEXT.md) · [Procedure inventory](docs/en/PROCEDURE_INVENTORY.md)

Run `python3 VERIFY.py`, the 637 self-contained tests and `install.py` to
inspect the plan. Stop Klipper before applying, then start it and update the
Fluidd groups with `python3 setup_fluidd.py --apply`. Keep the rollback
receipt.

[Install on Orange Pi](docs/en/INSTALL.md) ·
[Settings and Information](docs/en/SETTINGS_INFORMATION.md) ·
[Maintenance and Material](docs/en/MAINTENANCE_MATERIAL.md) ·
[Validation](docs/en/PRINT_CONTEXT.md)

G-code and converted Z-code share Start/End and AUTO saved-mesh selection. Maintenance adds Heat the platform; Settings adds persistent Full platform preheating. Use `python3 check-zcode.py --limits actual-limits.json file.zcode` for read-only whole-file preflight. Real Z-Suite corpus and physical printing remain separate acceptance evidence.

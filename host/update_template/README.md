# M300 host R15.6 — native menu and OEM sleep notice

[Polski](README_PL.md) · [Install](docs/en/INSTALL.md) · [Behaviour](docs/en/BEHAVIOUR.md) · [Status](docs/en/STATUS.md)

Update for the installed **M300 Classic native host R15.5 + MCU R14.4**.
Restores native menu routes lost in R15.5 and adds display inactivity
revision **0.2.0-M300-OEM-SLEEP**.

| After 5 minutes without operator input | OLED |
|---|---|
| Printing, paused, procedure, queued movement or heater target | Dimmed; live indications continue |
| Idle | Original moon + **Entering sleep mode**, then off after 10 seconds of acknowledged display |
| Knob gesture or external G-code request | Wake; the first invisible knob gesture is consumed |

The exact English text and 50×50 moon are verified against stock M300 1.3.1.
The original machine-sleep heater, motor and wake-up actions are not reproduced.
Native movement, heaters, fans, PID and SAVE_CONFIG retain their existing owners.

The installer updates the menu and M11 action list, adds four display files,
and adds a configuration include when needed. It preserves existing display
settings and supports the previous display revision 0.1.
Unknown local modifications are refused. Backups support exact rollback.

**Keep MCU R14.4 installed. This ZIP contains no firmware to flash.**
Do not reinstall the older complete R15.5 package after this update: it would
replace the repaired menu again.

Run `python3 VERIFY.py` and `python3 -m unittest discover -s tests -v`.
The self-contained suite has **71 tests**. Additional baseline, ARM build and
actual Klippy FILEOUTPUT checks are in REPORTS of the complete Actions artifact.
No physical printer was operated during this validation. See the audit for
remaining Z geometry, temperature and performance qualifications.

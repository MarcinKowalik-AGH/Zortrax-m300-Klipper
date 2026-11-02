# M300 host R15.7 — factory hardware revision and Z profile

[Polski](README_PL.md) · [Install](docs/en/INSTALL.md) · [Hardware variants](docs/en/HARDWARE_VARIANTS.md)

Update for installed M300 Classic native host R15.5/R15.6. Requires the matching
MCU R14.5 application for default factory selection. The MCU application is in
the complete Actions artifact, not inside this host-only ZIP.

Factory ID3 selects Z=800 before HW05, otherwise 400. Native stepper, M07 and
OLED status share the scale. ZORTRAX_HARDWARE_STATUS reports the factory revision,
configured/effective rotation distances and selected mode. Invalid identity is
not guessed. Explicit z_profile=config retains the operator-configured scale.

The installer preserves saved PID, extrusion calibration, configuration files
and existing display settings. It supports known R15.5/R15.6 module hashes,
creates an exact rollback receipt and refuses unknown local modifications.
R15.6 menu repairs and original moon / Entering sleep mode behaviour remain.
No extra runtime polling or motion interception is added.

Run python3 VERIFY.py, python3 -m unittest discover -s tests -v, then
python3 install.py to inspect the plan. The suite contains 92 tests.
Follow docs/en/INSTALL.md for the matching MCU/host update order. Public CI and
ARM compilation are software validation; physical Z travel still needs checking.

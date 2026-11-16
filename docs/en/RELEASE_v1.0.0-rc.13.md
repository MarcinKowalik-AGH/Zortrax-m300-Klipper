# M300 Classic RC13

Filament load and unload from the OLED, Fluidd or the console now work with
native Klipper Bed Mesh active. The filament procedure moves only the
extruder, then restores the G-code position state. The active mesh stays
in place. The motion guard continues to refuse unrecognized transforms and
applies the existing rules to procedures that move X, Y or Z.

## Update Klipper

When the printer is Ready, with printing and procedures finished and heater
targets off, run as the Klipper user:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

This update requires only the Klipper host on an existing installation
with MCU 1.0.5. The full package includes `MCU/M300_SD.zip` for first
installation. Use Fluidd at the existing address on port 4480. The separate
`--update-fluidd --port 4480` command is for an explicit website repair.
[First installation](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.13/docs/en/FIRST_INSTALL.md) ·
[Update guide](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.13/docs/en/INSTALL.md)

## Verification

Software regression tests exercise load and unload with active native
Bed Mesh and check the extruder-only motion, retained mesh and restored
parser state. At the next load or unload on the printer, confirm that
the procedure completes and compare the read-only `BED_MESH_OUTPUT` before
and after. Physical verification is pending. The beta.20 OLED illustrations
remain a historical reference.

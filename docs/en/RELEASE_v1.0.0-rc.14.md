# M300 Classic RC14

`START_PRINT` retracts filament by 10 mm after heating and any platform
stabilization. The retract completes before Z contact. After homing, Klipper
selects the mesh, approaches the purge start at safe Z and feeds 6 mm.
It then draws two long lines in Y and two in X at one commanded Z height.
The first X pass starts at the end of the return Y pass. An active mesh
still compensates the physical Z position. Klipper lifts on completion and
then gives control to the print file. Standalone Home Z and Bed Mesh use
their own measurement routines.

Dynamic Light stays white while the model prints, including during changes
in heater targets. Startup, pause and fault indications follow their
respective states.

## Update Klipper

When the printer is Ready, with prints and procedures finished and heater
targets off, run as the Klipper user:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

An installation already running MCU 1.0.5 only needs the host update.
The full package includes `MCU/M300_SD.zip` for first installation.
Fluidd remains available on port 4480. The separate
`--update-fluidd --port 4480` command is for explicit website repair.
[First installation](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.14/docs/en/FIRST_INSTALL.md) ·
[Update guide](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.14/docs/en/INSTALL.md)

## Verification

Software tests check the start sequence, all four purge lines and lighting
during model printing. The physical check is the next supervised print.
Observe the retract before Z contact, the four purge lines and the white
light once model printing begins. The beta.20 OLED illustrations remain a
historical reference.

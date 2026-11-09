# v1.0.0-beta.9 — split Home X/Y, coherent Fluidd/OLED and complete logo

For the **original Zortrax M300 Classic** with STM32F103, native host
R16.12 and MCU R14.18. Supersedes beta.8; carries forward the beta.7
safe upgrade hashes, beta.6 OLED navigation, beta.5 saved pad mesh view,
beta.4 OLED ACK recovery and beta.8 independent buzzer deadline.

## Individual X/Y homing and return to the OLED selected row

The original underlying native homing owner already supports G28 X and
G28 Y independently. The obsolete UI adapter navigated to
`motion_status` (whose first entry is Back) before starting the command,
making the selected Home X/Y row disappear.

Now OLED **Klipper** and **Zortrax M300 → Maintenance** dispatch exactly
the same guarded owner as the matching Fluidd macros:

| OLED choice | Fluidd macro | Native motion | Precondition |
|---|---|---|---|
| Home X | `ZORTRAX_HOME_X` | `G28 X` | Safe Z clearance only |
| Home Y | `ZORTRAX_HOME_Y` | `G28 Y` | Safe Z clearance only |
| Home XY | `ZORTRAX_HOME_XY` | `G28 X Y` (Y, X) | Safe Z clearance |
| Home Z | `ZORTRAX_HOME_Z` | `G28 Z` | Homed X **and** Y; 180 C minimum |
| Home XYZ | `ZORTRAX_HOME_ALL` | `G28` (Y, X, Z) | Normal native homing safeguards |

The new macros are added idempotently by the host installer to an existing
config, preserving operator-defined macros and saved settings.
All five functions share `ZORTRAX_PROCEDURE_START`, native operation
tokens, phase snapshots and automated OLED/Fluidd presentations.
A normal OLED click stays on the previously selected row, including
fast completed moves; the procedure may temporarily display its progress
and restores the original row on completion. No `motion_status` Back
screen is opened as a side effect of clicking a home action.

The former rejection `Home XY first, or use G28 for XYZ` was
ambiguous: it was emitted by **Home Z** while one/both XY axes were
unhomed, not by the X/Y-only operations. It now explicitly says that
X+Y can be obtained by separate X and Y homing in either order,
by Home XY, or with full Home XYZ. Tests assert that Home Z refuses
to move or heat when only one axis is known, while X then Y then Z
works without repeating X or Y.

**Safety is unchanged:** 5 mm initial Z clearance before any lateral
movement; PC7 release check; protected print/session checks; 180 C
contact homing for Z; five native refinement contacts and final Z
separation. No new force-move, motor override, firmware or UART changes.

## Full Klipper logo with its wordmark

The previous beta.8 icon showed only the large V. Beta.9 places both
the V/nozzle mark **and the lowercase word `klipper`** inside the
original 50×50 printer outline, leaving its stroke thickness, full
contrast and animated upper head unchanged. The logo pixels use
three 4bpp brightness values: 7 (original slate), 11 (original red)
and 15 (wordmark; same as OEM full brightness). Actual physical OLED
emits varying brightness of cyan, not literal RGB.
[Native 50×50 reference](../assets/menu-symbols/klipper-full-logo-50x50.svg).
No font files, SVG parsing or new MCU flash.

## Upgrade the installed Orange Pi

With the printer **Ready** and idle:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Refresh Fluidd with Cmd+Shift+R after installation. The verified release
contains the exact beta.8 deployment hashes in the safe-upgrade list.
An unknown locally edited module still causes a refusal without
overwriting it.

## Required validation

The beta release is published only after its matching successful
GitHub Actions build: **690 host tests**, nine repository contracts,
migration checks through beta.8, MCU ARM build, native Klippy FILEOUTPUT,
OLED artwork/return tests, compiled Fluidd and release SHA-256 checks.
These are software validations; confirm actual home X/Y/Z travel and
speaker on the printer before unattended printing.

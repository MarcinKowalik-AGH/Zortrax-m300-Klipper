# RC1 — one OLED, Fluidd and Klipper control surface

The public version is **1.0.0-rc.1**. There are no parallel motion procedures:
buttons call the same procedure owners as the OLED. Settings without an argument
open the shared selector; an explicit argument updates the same persistent value.

| OLED Settings entry | Public macro | Optional argument |
|---|---|---|
| Light | ZORTRAX_LIGHT | MODE=DYNAMIC/WHITE/DISABLED |
| Buzzer | ZORTRAX_BUZZER | STATE=ENABLED/DISABLED |
| Sleep mode | ZORTRAX_SLEEP_MODE | STATE=ENABLED/DISABLED |
| Language | ZORTRAX_LANGUAGE | English only |
| Models sorting | ZORTRAX_MODELS_SORT | MODE=DATE/NAME/NAME_CASE/SIZE |
| Full platform preheating | ZORTRAX_FULL_PLATFORM_PREHEAT | STATE=ENABLED/DISABLED |
| OLED brightness | ZORTRAX_OLED_BRIGHTNESS | LEVEL=1..16 |
| LED brightness | ZORTRAX_LED_BRIGHTNESS | LEVEL=1..16 |

Brightness is validated as an integer, never rounded from a float. A bare click
does not change settings. The physical slider and remote setting share existing
NVM/events. ZORTRAX_SCREEN is still a read-only display status command.

Homing, autocalibration, pad mesh, heating, material handling, print controls and
PID keep their existing safety owners. Platform movement uses the same native
service: physical hold on OLED, a bounded step in Fluidd. Current procedure is
available through ZORTRAX_PROCEDURE and Maintenance; it reopens a session, not a
new operation. ZORTRAX_DIAGNOSTICS reads configuration, board, OLED and cooling.
The original fan test is retained as an OEM maintenance function.

The OLED root contains Klipper and Zortrax M300, without Service / Tests.
Known stock TEST_ZORTRAX_XY/STATUS, ZORTRAX_PRINT and ZORTRAX_OLED_PERF wrappers
are retired. Custom bodies are preserved, not silently deleted. Old lab entries
are hidden even when stale Fluidd preferences mark them visible; unrelated user
macros and populated custom categories are retained. Developer regression tests
remain in the repository and run in isolated harnesses, not as installed buttons.

Information shows the RC host version and a concise numeric MCU version. Full
firmware IDs remain in machine diagnostics for compatibility; the physical MCU
is not reflashed or relabeled by the host updater. Generic package names replace
development suffixes: M300_HOST, M300_FLUIDD.zip, MCU/M300_SD.zip. Historical
release artifacts and signed/checksummed evidence are not rewritten.

Upgrade only while idle and Ready, not paused:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Refresh Fluidd. Qualified Z values, saved mesh, PID, UART and all current motion
and thermal safeguards remain unchanged. No MCU flash is required. RC1 is a
release candidate, not a claim of completed hardware acceptance. See the
[Polish UI matrix](../pl/RC1_UI.md), [macro catalogue](../pl/MACRO_REFERENCE.md),
[acceptance register](../pl/ACCEPTANCE_REGISTER.md) and
[illustrated OLED handbook](../pl/OLED_FUNCTIONS.md). Its 65 beta.20 screens
remain a labeled historical visual reference, not fabricated RC1 screenshots.

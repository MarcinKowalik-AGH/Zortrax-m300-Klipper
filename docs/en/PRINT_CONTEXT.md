# Native print contexts on OLED and Fluidd

| OLED context | Operator action | Shared native behavior |
|---|---|---|
| PRINTING | Hold the knob continuously for 10 seconds | PAUSE stops the native virtual SD worker and saves the pause state. Fluidd Pause leads to the same menu. |
| PAUSE MENU | Resume the print | RESUME restores the saved position and resumes the same file. |
| PAUSE MENU | Change the material | The existing CHANGE wizard owns the screen until the change ends. The print remains paused for explicit Resume. |
| PAUSE MENU | Stop the print → Yes, stop the print | CANCEL_PRINT turns off the heaters and delegates cancellation to native Klipper. Fluidd Cancel uses the same command. |
| PRINTING DONE | Remove the model, then hold for 10 seconds to reprint | Starts the retained copy as a new native job. A short press closes the OLED notice. |

The OLED waits for native EOF and for queued motion to drain before showing
PRINTING DONE. A completed job with an eligible snapshot offers reprint.
A cancel, error, incomplete read or restart leaves no eligible copy. The
10-second thresholds are the requested host policy. The recovered stock
pause and completion handlers use different timing and separate confirmation
logic.

A hold requires fresh encoder samples throughout and an acknowledged OLED
frame for the current print. Releasing, losing the panel link, waking a
hidden display or switching print identity ends the gesture. A release
from the pause hold cannot select a row in the new menu. Ordinary menu
navigation keeps its existing knob behavior.

## Fluidd

Pause, Resume and Cancel on the dashboard operate on native Klipper state.
A physical SD print has a unique virtual filename in print history. Fluidd's
dashboard Reprint sends that filename through Moonraker, and Klipper matches
it to the retained copy of that exact print. An older virtual filename is
refused when its copy is gone. The OLED shows the friendly filename.

For regular host files the standard Fluidd Reprint opens the selected file
by name. To replay the retained bytes of the last eligible native print,
open **ZORTRAX_REPRINT** in the M300 macro group or run it in the console,
remove the model, then use **Reprint** in the confirmation dialog. The same
exact-copy action is available from the OLED. A regular native file above the
configured snapshot size limit remains printable through Fluidd. Exact
replay is available only for jobs the host could retain and verify.

[Fluidd status and Reprint source](https://github.com/fluidd-core/fluidd/blob/develop/src/components/widgets/status/PrinterStatusCard.vue) ·
[Moonraker print start](https://github.com/Arksine/moonraker/blob/master/moonraker/components/klippy_apis.py)

A native M25 SD pause does not save PAUSE_STATE. Its OLED screen directs
the operator to M24. The contextual PAUSE MENU is available for a saved
native PAUSE. Normal pause/stop run at the native command boundary.

[Procedure inventory](PROCEDURE_INVENTORY.md) · [Installation](INSTALL.md)

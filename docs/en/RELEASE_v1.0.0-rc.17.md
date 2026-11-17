# M300 Classic RC17

RC17 updates the Klipper host on the Orange Pi. A printer already running MCU 1.0.5 needs the host update only. The first-install archive includes `MCU/M300_SD.zip`. Fluidd uses port 4480.

| Function | RC17 behavior |
|---|---|
| Orca print | The active file owns START and END. Operator homing during an active print is rejected. |
| Material change | When M600 cannot park with sufficient clearance it holds XY and leaves the print paused for a manual Resume. |
| Bed mesh | Select a saved plate with `BED_MESH_PROFILE LOAD=name`. `MESH=AUTO` checks the selection before motion and loads it after homing. Select `MESH=NONE` to print without compensation. |
| Hot nozzle | Standalone Home Z and bed mesh retract 10 mm and restore 10 mm on successful completion. START retracts once and feeds 6 mm before the purge lines. |
| Print time | The host reconciles previously credited minutes before a new counter transfer. A full G2/G3 circle with extrusion starts the model clock. |
| Fluidd repair | Explicit `--update-fluidd --port 4480` exchanges the web directory atomically and verifies HTML, JavaScript and CSS over HTTP. |

Update with the printer idle. The ordinary host update preserves the web site and nginx configuration. After updating, check `PRINT_CONTROL_STATUS`, `ZORTRAX_HARDWARE_STATUS` and `ZORTRAX_INFO REFRESH=0`. Hardware acceptance covers two ID0 writes, a cold restart, and the pause, change, resume and end sequence from OLED and Fluidd. Manual OLED illustrations use the beta.20 visual baseline.

[Update instructions](INSTALL.md) · [First installation](FIRST_INSTALL.md)

# M300 Classic RC27 — Zortrax operator menu in Fluidd

Choose **ZORTRAX_MAIN_MENU** in the **ZORTRAX M300** macro group in Fluidd or in OrcaSlicer's Device tab. The menu shows Models, Maintenance, Material, Settings and Information in the same order as the OLED.

- **Material → Unload the material** starts the shared procedure. When prompted, confirm on the OLED or in Fluidd. Use `ZORTRAX_PROCEDURE` to reopen the current phase after closing the dialog.
- **Maintenance** includes homing, heating, calibration, platform movement and the fan test. A platform movement button takes one 1 mm step. Hold the physical knob for continuous movement.
- **Models** lists host files and the physical SD card when card access is qualified. Select a file, choose **Refresh** after import finishes, then choose **Start printing** to approve the prepared model.

With the printer idle and Ready and heater targets off, run the host update from the existing `orange-pi` checkout:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

This menu uses the installed Fluidd on port 4480 and MCU 1.0.8. Only the host update is required for this feature. The `MCU/M300_SD.zip` archive is for a separate firmware update. The manual's beta.20 illustrations document an earlier interface.

If the web files need a separate repair, the installer provides `--update-fluidd --port 4480`. [Update and recovery instructions](INSTALL.md).

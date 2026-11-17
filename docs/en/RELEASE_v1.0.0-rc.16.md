# M300 Classic RC16

| Command | Machine motion |
|---|---|
| `PAUSE`, `M25`, `M601` | After queued moves finish the head holds its current XY. The bed lowers by 5 mm by default within Z travel. The motors hold position. |
| `RESUME` | Klipper restores the print temperatures and position, then continues the same file. |
| `M600` or Change the material from the pause menu | The head travels to the service park at the clearance already reached. Material transport starts after that move drains. |
| Orca `END_PRINT` | The bed descends by 300 mm or to the configured Z limit. The head then parks at the rear right (X300 Y305 by default). Once motion drains, the heaters and part fan switch off and the file reaches EOF, the OLED shows **PRINTING DONE**. |

With a last print position of Z250 and a limit of Z300 the bed descends by 50 mm.
If the remaining travel falls below the required clearance (5 mm by default), the bed uses the available travel and the head holds XY.
**Stop the print** in the pause menu calls `CANCEL_PRINT` and cancels the job.

## Orange Pi update

When the print and all procedures have finished, the heater targets are off and Klipper reports Ready, run as the Klipper user

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Run `PRINT_CONTROL_STATUS` in the Fluidd console. The expected revision is `0.13.16.41-END-PARK`.
Use the existing Fluidd site on port 4480. The `--update-fluidd --port 4480` option is for a separate site repair.
An existing installation running MCU 1.0.5 needs the host update only. The full first-install package includes `MCU/M300_SD.zip`.
[First installation](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.16/docs/en/FIRST_INSTALL.md) · [Update guide](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.16/docs/en/INSTALL.md)

Software tests exercise pause and resume with an active mesh, material-change parking, low and tall models, slow Z travel and cancellation during descent. Physical RC16 verification is pending. The illustrated manual uses beta.20 OLED images.

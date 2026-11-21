<!-- Marcin Kowalik <mkowalik@agh.edu.pl> | USER_GUIDE.md - Guides an M300 Classic operator from installation through printing, material changes and fault diagnosis. -->
# M300 Classic operator handbook

This guide follows a job on the original M300 Classic with host 1.0.1, MCU 1.0.8 and the M300 edition of Fluidd on port 4480. The physical menu uses English labels. [Polski](../pl/USER_GUIDE.md).

## Choose the installation path

| Starting point | Procedure | What to check afterward |
|---|---|---|
| New SBC and compatible SD bootloader already on the printer | Follow the [first-install guide](FIRST_INSTALL.md). The versioned full ZIP contains the complete Klipper tree, MCU application, Fluidd and installer. Run the installer plan before applying it. | Klipper reaches Ready and both heater targets are zero. |
| Working M300 Klipper installation | Update from the published `orange-pi` branch as the Klipper user while idle, with both heater targets off. [Update instructions and rollback](INSTALL.md). | `ZORTRAX_INFO REFRESH=0` reports the installed host and MCU versions. |
| MCU needs the paired application | Verify the MCU ZIP, extract `M300APP.M3B` and follow the [SD application procedure](MCU_FIRMWARE_1.0.8.md). | `ZORTRAX_MCU_STATUS` reports MCU 1.0.8. |
| Empty Fluidd page, or a damaged deployment checkout | Use the matching [Git or Fluidd recovery procedure](INSTALL.md). | The page and its JavaScript asset both contain data, and the Console opens. |

## Prepare the plate and start a print

1. Check the plate seating, the nozzle and the contact fields. In Fluidd open `http://<printer-host>:4480/`. Check `STATUS`, `ZORTRAX_HARDWARE_STATUS` and `QUERY_PROBE`. With the nozzle clear of the plate, the probe should be open. On a new installation check the reported board and effective Z scale before moving the machine. [Hardware variants](HARDWARE_VARIANTS.md).
2. If the plate needs mechanical adjustment, choose **Zortrax M300 → Maintenance → Autocalibration** and follow the screw prompts. For a compensation profile, use **Tune → Calibrate** or `BED_MESH`. Wait for the measurement to complete. `SAVE_CONFIG` stores the profile and restarts Klipper. When Ready again, select it with `BED_MESH_PROFILE LOAD=m300_pads` and inspect it with `BED_MESH_OUTPUT`. [Contact leveling](LEVELING.md) · [Mesh measurement and activation](../pl/BED_MESH_AND_LEVELING.md).
3. Use the M300 Classic printer, nozzle and filament presets in OrcaSlicer. The machine start G-code calls the M300 start procedure once, passing the material's temperatures. The end G-code contains `END_PRINT`. Print the sliced file from the Device tab or Fluidd. For a model on the printer's card, open **Models**, select the source and file, then approve the prepared model. [OrcaSlicer profiles](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Orca-Slicer) · [Supported SD formats](MODELS_SD.md).

Machine start G-code for these OrcaSlicer presets:

```gcode
START_PRINT EXTRUDER_TEMP=[nozzle_temperature_initial_layer] BED_TEMP=[bed_temperature_initial_layer_single] MESH=AUTO
```

After heating, START retracts 10 mm before homing, loads the selected saved mesh, returns 6 mm and primes with two Y passes followed by two X passes. At the Y/X transition the commanded purge height is constant. With `MESH=AUTO`, selection falls back to `m300_pads` or the sole saved profile when there is no remembered choice. An absent or ambiguous selection stops preparation. Use `BED_MESH_OUTPUT` to check activation. [Start and print contexts](PRINT_CONTEXT.md).

## Pause, change colour and finish

| Action | What the operator sees and does |
|---|---|
| Pause | Use **Pause** in Fluidd or the OLED print controls. Ordinary pause holds the current XY, lowers the bed by 5 mm by default and keeps the motors engaged. |
| Change colour | Choose **Change the material** or use `M600`. The head parks at the service corner when clearance allows. Wait for withdrawal, insert the new filament when prompted and confirm. |
| Purge | When the flow confirmation appears, set length and speed in **Tool**. **Extrude** pushes filament and **Retract** withdraws it. Repeat until the new colour comes out cleanly. Confirm flow, then choose **Resume**. The same buttons work after an ordinary pause has settled. |
| Standalone load or unload | Select **Material** on the OLED or open `M300_MAIN_MENU` in Fluidd. After automatic transport ends the nozzle stays at the selected target for manual feeding until normal idle cooling or manual switch-off. |
| End or cancel | Both lower the bed by up to 300 mm within Z travel, then park at X300 Y305 when there is clearance. A normal end shows **PRINTING DONE**. **Cancel** closes the file and turns off heating before the descent. Only a paused job can be resumed. |

After a material change, the measured and target nozzle temperatures must both reach the extrusion threshold. With a reading of 230°C and a target of 150°C, choose **Reheat to check flow** on the OLED or **Resume** in Fluidd. The print stays paused after reheating. Purge, check the visible flow and choose **Confirm material flow** or enter `FILAMENT_READY`. An accepted manual retraction clears the confirmation. After purging again, confirm the flow and explicitly choose **Resume**.

The four settings in `[m300_filament]` are `unload_temperature`, `unload_speed`, `load_temperature` and `load_speed`. Each accepts `auto` or a number. Auto selects 240°C and 2 mm/s in each direction. The fields in Fluidd's Tool panel set distance and speed for a manual click. After a long pause reheat to the material's working temperature before purging. [Material procedures](MAINTENANCE_MATERIAL.md).

## Display and print-time settings

The OLED and `M300_MAIN_MENU` in Fluidd share Models, Maintenance, Material, Settings and Information. A confirmation from either surface advances the current procedure. To reopen its dialog use `M300_PROCEDURE`.

In **Settings**, **OLED dim time** and **OLED sleep time** each edit one value from 1 to 60 minutes since the last interaction. Turn and press to save. The board retains the preferred DIM. Shortening SLEEP below it shortens effective DIM, and lengthening SLEEP restores DIM up to its preference. The first knob gesture wakes the panel. OLED and cabinet LED brightness have independent levels from 1 to 16. [Display controls and readback](SETTINGS_INFORMATION.md).

Read `ZORTRAX_HARDWARE_STATUS` for the factory counter. After a completed write, `CURRENT` with `factory_counter_pending: false` means the MCU is up to date to the whole minute. Sub-minute time remains on the host. After a normal power cycle compare `factory_print_minutes` to the previous reading. [Counter states and reconciliation](MCU_FIRMWARE_1.0.8.md#read-the-counter).

## Diagnose a problem

| Symptom | First check |
|---|---|
| Device sidebar stops navigating | Click the circular reload arrow in the Fluidd toolbar in OrcaSlicer's Device tab. If assets are empty or missing, follow the [Fluidd recovery guide](INSTALL.md#diagnose-a-blank-or-unreachable-fluidd-page). |
| Nozzle will not feed during a pause | Use `PRINT_CONTROL_STATUS` and `ZORTRAX_FILAMENT_STATUS`. Wait for parking or automatic transport to finish. Verify that the nozzle has heated and still has a working target. |
| The factory counter reads `AWAITING_IDLE` | Read `factory_counter_wait_reason`. Keep the printer idle with heater targets off for a new read. The host keeps outstanding time. |
| An OEM fault or link error appears | Collect `ZORTRAX_ERROR_STATUS`, `ZORTRAX_LINK_STATUS` and `klippy.log` before restarting. For verbose M300 diagnostics set `debug: True` in the existing `[m300_mcu]` section and reload while idle. Return to `False` for normal logging. [Error catalogue](ERRORS.md). |

Hardware results, including the operator's completed print and the counter readback after power cycling, are documented in the [acceptance register](../pl/ACCEPTANCE_REGISTER.md). Results that still require a printer are recorded there alongside the specific operation to verify.

# Printer activity symbols

## Homing presentation

Fluidd uses its existing X, Y, XY, Z and All home buttons. The matching button
shows its normal busy indicator, including when a macro, the OLED or another
client starts homing. The phase text is attached to that button as a tooltip
or title. The circular control highlights the matching home symbol. Its Y
button uses the Y wait key. No homing procedure opens or closes a Fluidd
prompt dialog; native command errors remain visible in the console and the
standard error notification.

The state comes from existing Moonraker subscriptions to `m300_motion` and
`m300_procedures`. Phase text is accepted only for the current token and
phase. Completion, cancellation, a fault or a disconnected printer clears
the remote busy indication. Ordinary Fluidd waits continue to work for all
printers. No extra MCU query or display transfer is introduced.

OLED homing retains the original M300 Classic 1.3.1 four-frame hourglass
at `0x0801c2b8`, with its 500 ms frame interval. Original sprite bytes and
their SHA-256 checks are unchanged. The phase text still comes from the
same procedure view. Maintenance continues to contain Homing XY, Homing Z
and Homing ALL immediately below Autocalibration.

## Existing visual vocabulary

The M300 runtime contains 37 audited 50 × 50 descriptors. The Inventure r0323
reference atlas contains 45 resources, including 13 animated resources with
40 animation frames. The inspected reference sheets were
`01_ATLAS_45_ZASOBOW(1).png` and `03_ATLAS_40_KLATEK_ANIMACJI(1).png`.
The Inventure artwork is a visual reference; it is not installed into M300
by this update.

| Activity | Existing source vocabulary | Use |
| --- | --- | --- |
| Homing / waiting | Four-frame hourglass in both printers | Keep original M300 animation |
| Manual leveling | Platform, screw and circular direction arrows | Keep audited OEM screw instructions |
| Load / unload | Filament transport, spool and insertion/removal arrows | Reuse existing M300 animations |
| Printing | Nine-frame progress ring | Reuse original progress vocabulary |
| Pause / resume | Circled pause bars / play arrow | Reuse original symbols |
| Completion / cancel | Circled check / cross | Reuse original symbols |
| Warning / failure | Triangle or octagon with exclamation mark | Reuse original symbols |
| Sleep | Crescent moon | Keep existing OLED sleep behavior |
| Models / files | Cube, folder and file check | Keep existing menu symbols |
| Maintenance / settings | Crossed tools / gear | Keep existing menu symbols |
| Information | Circled lower-case i | Keep original information symbol |

## Additional symbol drafts

These are new project designs inspired by the two visual vocabularies.
They are not extracted OEM graphics and are not assigned to runtime OLED
screens in this update. Each SVG has a 50 × 50 viewBox and four discrete
frames at 500 ms. Runtime integration can use pre-rendered 4bpp frames;
SVG rendering on the Orange Pi is not needed during printer operation.

![Draft symbol review sheet](../assets/ui-symbols/preview.png)

| Symbol | Printer function | Proposed movement | Draft |
| --- | --- | --- | --- |
| Bed mesh | Native 25-contact map | Measurement dot visits platform pads | [SVG](../assets/ui-symbols/bed_mesh.svg) |
| Heat the nozzle | Hotend heating | Rising heat waves below the nozzle | [SVG](../assets/ui-symbols/heat_nozzle.svg) |
| Heat the bed | Bed heating | Heat waves rise from the platform | [SVG](../assets/ui-symbols/heat_bed.svg) |
| Cooling | Cooling after heating or a print | Temperature marker moves downward | [SVG](../assets/ui-symbols/cooling.svg) |
| Upper fan | Upper fan test and cooling status | Three blades rotate; upper marker stays fixed | [SVG](../assets/ui-symbols/fan_upper.svg) |
| Lower fan | Lower/model fan test | Three blades rotate; lower marker stays fixed | [SVG](../assets/ui-symbols/fan_lower.svg) |
| Read SD card | Physical SD listing and file import | Data marker moves across the card | [SVG](../assets/ui-symbols/sd_read.svg) |
| Prepare model file | File validation and Z-code preparation | Data marker moves between files | [SVG](../assets/ui-symbols/file_convert.svg) |
| Clean the nozzle | Operator cleaning instruction | Brush moves under the nozzle | [SVG](../assets/ui-symbols/clean_nozzle.svg) |
| Printer connection | Host–MCU connection status | Marker follows the link arrows | [SVG](../assets/ui-symbols/link_status.svg) |
| OLED brightness | Existing 16-level display setting | Display and segmented bar change together | [SVG](../assets/ui-symbols/oled_brightness.svg) |
| LED brightness | Existing 16-level lighting setting | Lamp rays and segmented bar change together | [SVG](../assets/ui-symbols/led_brightness.svg) |

Do not show an animated activity symbol when its associated operation is
inactive. In particular, a connection symbol must not imply healthy motion
or hardware qualification, and fan artwork must not imply measured RPM on
hardware that has no tachometer. These drafts add no controls or capabilities.

Reproduce the SVGs and contact sheet with `python3 ci/render_ui_symbols.py`.
Render the PNG from `preview.svg` with CairoSVG. The catalog JSON records
geometry, frame cadence, origin and the inactive runtime status.

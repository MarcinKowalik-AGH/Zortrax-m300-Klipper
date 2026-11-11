# Models from the MCU SD reader

R16.9 adds native printing from the M300 Classic card slot. The host reads a
FAT16 or FAT32 card through the existing MCU R14.5 read-only SPI1 protocol.
Once the printer has copied and checked a model, Klipper runs the local copy.
The original file and card contents are preserved.

## Enable the card reader

Use R16.9 on the Orange Pi with MCU R14.5. With the printer idle, edit the
existing `[m300_sd]` section in the printer configuration or its include.
Set the existing reader opt-in to true, then restart Klipper.

```ini
[m300_sd]
sd_qualified: True
```

Keep a single `[m300_sd]` section. `ZORTRAX_SD_STATUS` reports whether the
option is enabled and the last card error. Start with a known FAT16/FAT32
card and a small file. The first hardware check is listing a folder and
importing a model without pressing Start printing.

## OLED

1. Open **Zortrax M300 → Models**. The menu opens the SD root when enabled.
2. Open a folder or choose a file. The preview shows the import state.
3. Wait for **Start printing**. Check the displayed filename, format and
   Z-code heater targets before selecting it. **Back** cancels the import
   or discards the prepared copy.
4. The OLED opens native Print status. Use Pause, Resume or Cancel there
   or in Fluidd. Use the existing Change the material option during pause.

The Models root also offers Host files from Klipper's existing G-code folder.
The MCU reader is idle once the local copy is ready.

| File | Preparation | Execution |
|---|---|---|
| `.gcode`, `.gco`, `.g` | Size, UTF-8 and line checks, then a read-only local snapshot | Native Klipper G-code, with the printer's configured slicer start/end commands and macros |
| `.zcode` | Check the M300 header, model family, every record and CRC, motion limits and temperatures before converting | Shared native START_PRINT / END_PRINT, AUTO saved mesh, optional platform soak and bounded final park |

For Z-code, the decoded coordinates use the file's X/Y/E scales of
640/640/960 and Z scale of 400 or 800. The native motion configuration
determines the actual steps. Startup requires zero XYZ G-code offsets and
uses the existing native G28 procedure through the shared START_PRINT owner. A file pause requires explicit Resume.

The binary support covers the recovered Classic M300 1.3.1 subset, model IDs
20–29. The Inventure converter smoke file in the project has model ID 10,
Z scale 802 and opcode 0x13. The M300 reader rejects it. A converter can
share its framing and CRC code when it gains a dedicated M300 output
profile with the correct heater and motion records. Changing the header
alone leaves different command semantics.

The bundled M300 Classic OrcaSlicer profile starts the nozzle at 180 °C for
contact homing. For files with that recognized startup block, the local
execution snapshot sends the nozzle setpoint before the bed wait. This
heats both at once while preserving the bed wait, homing and final nozzle
temperature. The same applies to Fluidd jobs captured within the snapshot
size limit. The original G-code remains on disk for other uses.

## Fluidd console

```gcode
ZORTRAX_SD_STATUS
ZORTRAX_BROWSER_LIST SOURCE=SD
ZORTRAX_BROWSER_PREVIEW GENERATION=<listing generation> INDEX=<zero-based index>
ZORTRAX_MODELS_STATUS
```

The Models browser hides the Windows metadata folder `System Volume Information`
at the physical SD root. A card with no supported files or user folders
there will show an empty listing. Omit `PATH` for the root, or use a relative directory path such as
`PATH=MODELS`. For files on the Orange Pi, use `SOURCE=HOST`.
When status reports `READY`, use its token with
`ZORTRAX_MODELS_START TOKEN=<token>`. To abandon the selection or stop
copying, use `ZORTRAX_MODELS_CANCEL_IMPORT TOKEN=<token>`. After start, use
the usual native print controls.

The current defaults admit text source files up to 16 MiB and binary source
files up to 8 MiB. Binary compilation is also limited to 250,000 records and
16 MiB of resulting G-code. Physical imports use the separate size and
timeout in `[m300_sd]`. The directory limit is 50 selectable entries.
Large files can take time to copy over the MCU UART.

Software validation covers modeled card sectors and native Klippy FILEOUTPUT.
The first real card transfer, representative M300 Z-Suite exports and a
physical print remain acceptance checks. Start those checks with a small,
known M300 job.

[Klipper virtual SD and pause/resume](https://www.klipper3d.org/Config_Reference.html#virtual_sdcard)

From print controller 0.13.16.29, converted Z-code uses `START_PRINT ... MESH=AUTO` and `END_PRINT`, like slicer G-code. AUTO loads an existing `m300_pads` profile after homing or explicitly clears compensation if none exists; an explicit missing profile is refused. Full platform preheating is captured from persistent settings. The read-only `check-zcode.py --limits actual-limits.json file.zcode` utility in the host package validates files without sending printer commands. This does not widen the supported opcode subset or qualify a physical Z-Suite corpus.

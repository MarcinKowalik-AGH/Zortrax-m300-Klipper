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
| `.zcode` | Check the M300 header, model family, every record and CRC, motion limits and temperatures before converting | Native G-code with heat, M300 XYZ homing, the converted moves and heat/fan shutdown at completion |

For Z-code, the decoded coordinates use the file's X/Y/E scales of
640/640/960 and Z scale of 400 or 800. The native motion configuration
determines the actual steps. Startup requires zero XYZ G-code offsets and
uses the existing native G28 procedure. A file pause requires explicit Resume.

The binary support covers the recovered Classic M300 1.3.1 subset, model IDs
20–29. The Inventure converter smoke file in the project has model ID 10,
Z scale 802 and opcode 0x13. The M300 reader rejects it. A converter can
share its framing and CRC code when it gains a dedicated M300 output
profile with the correct heater and motion records. Changing the header
alone leaves different command semantics.

## Fluidd console

```gcode
ZORTRAX_SD_STATUS
ZORTRAX_BROWSER_LIST SOURCE=SD
ZORTRAX_BROWSER_PREVIEW GENERATION=<listing generation> INDEX=<zero-based index>
ZORTRAX_MODELS_STATUS
```

Omit `PATH` for the root, or use a relative directory path such as
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

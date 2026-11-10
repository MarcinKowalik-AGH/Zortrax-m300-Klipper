# M300 Classic beta.21 — toned activity icons on the host and MCU

Supersedes beta.20. Host R16.12; MCU **0.13.14.19-TONED-OLED-UART8**. Artwork revision ACTIVITY-TONES-1. This changes presentation only, not motion, heaters, fault policy, UART protocol or the bootloader.

## Changes

24 activity designs / 96 frames keep their 50×50 footprint, original bright stroke cores and 500ms cadence, adding subtle intermediate edge luminances (primarily 0,2,4,15; also 6 in one design). They remain precomputed native 4bpp bitmaps. No runtime image filter, new timer or browser interpolation is added.

The original firmware graphics, separate Home/Move icons and the three-tone Klipper logo are **unchanged**. This is not a claim that every new symbol has been redrawn. [Illustrated Polish notes](../pl/RELEASE_v1.0.0-beta.21.md).

The MCU's autonomous waiting/disconnect/error screens now use matching 4bpp scanlines with flash deduplication, preserving the **128-byte scanline buffer** and the original scheduler/ownership boundaries. Error titles and first-fault classification are unchanged. The linker must still fit the existing 64KiB application region and 20KiB RAM limits.

## Host upgrade

With the printer **idle and Ready**, on Orange Pi:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Refresh Fluidd with Cmd+Shift+R. The installer recognizes the exact previous artwork checksum and still rejects unknown edits.

This alone updates normal menus on both the physical OLED and Fluidd: MCU R14.18 already accepts native 4bpp host frames. To update the **independent MCU waiting/fault screens**, separately flash **MCU/M300APP.M3B** from this release (also provided as **MCU/M300_R14_19_SD.zip**) through the existing M300 SD bootloader procedure. Stop Klipper while idle before flashing, retain the current UART baud, do not erase the bootloader/factory data, remove the SD update file after success and restart Klipper. The M3B contains an application at 0x08008000, not a complete Flash image. See [first installation, MCU application](FIRST_INSTALL.md). Verify the new revision with ZORTRAX_MCU_STATUS. The host installer never flashes the MCU automatically.

## Validation

The release requires the full matching ARM/host/native-Klippy/Fluidd CI, previous-install migration safeguards, exact per-pixel host/MCU asset agreement and native C rendering, startup/handover/timeout checks, RLE reconstruction for all 96 icons, fixed cache/geometry/cadence checks, browser pixel/layout regressions, and package integrity. This is software validation, not a physical OLED acceptance test.

Tonal edges can cost bandwidth: isolated icon RLE payload averages rise from about 498 to 625 bytes/frame across 96 frames (excluding protocol overhead and unrelated screen content). Packet bounds and animation timing are unchanged. The report is REPORTS/OLED_TONES.json; no unmeasured latency guarantee is made.

The existing 65-screen handbook remains an explicitly versioned beta.20 reference. This release supplement and its image document the new activity artwork; controls and functions have not changed.

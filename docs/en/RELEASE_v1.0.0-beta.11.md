# v1.0.0-beta.11 — read-only live OLED preview in Fluidd

Zortrax M300 Classic (STM32F103), Klipper host R16.12, Fluidd 1.37.7.
Supersedes beta.10 with no changes to physical motion, homing, heaters,
probe, menu labels, buzzer, UART, DMA, RLE or MCU executable.

## UI

The Temperature card gains a full-width OLED preview **beneath the
temperature chart** on the Dashboard, matching the available card width.
It preserves the 4:1 aspect ratio of the original 256×64 monochrome/16-tone
OLED. A Show/Hide control collapses the preview. It is observation only:
mouse/touch input cannot operate the rotary encoder or trigger any G-code.

For non-M300 printers, no preview is displayed. On a disconnected MCU,
the preview hides the old host frame and reports that the MCU-local
waiting/error screen is unavailable as a readback.

## Transport contract

Klipper retains the original `m300_oled_transport.py` and all SPI/DMA
MCU code unchanged. The existing `m300_oled` status adds a read-only
`oled_preview` with `online`, `sequence`, `width`, `height`,
`format=indexed4-png` and `image_base64`.

The frame is taken from **`stream.previous` after the last full ACK**;
pending/unacknowledged frames are not presented as confirmed. A bounded
2 Hz / 500ms change detector packages the original native 8192-byte,
4bpp row-major SSD1322 bytes losslessly into indexed PNG (16 defined
RGB preview shades). The PNG is significantly smaller than a raw frame.
No extra SPI/UART traffic is generated. Moonraker already subscribes to
all registered Klipper status objects; this field is delivered by the
existing WebSocket. There is no new unauthenticated endpoint or exposed
port. All image bytes are validated before the browser accepts a
`data:image/png;base64` URL; SVG/HTML content cannot be substituted.

## Deployment

With Klipper **Ready** and the printer **idle**:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Then hard-refresh Fluidd with Cmd+Shift+R on Mac. The transactional
installer recognizes published beta.10 host module hashes and copies the
new `m300_oled_preview.py` module. **MCU reflashing is not needed.**

## Verification

Full Actions validation covers **699 host tests** (including six new
PNG/ACK/throttle/offline tests), nine repository contracts, existing
homing/PC7/thermal/procedure/ACK/RLE tests, MCU ARM compilation,
MCU panel simulation, pinned Klippy FILEOUTPUT, frontend Vitest/TypeScript/
ESLint and a production Fluidd build. The new frontend test covers status
selection, offline handling and invalid image inputs. Final pixel
appearance and bandwidth on the physical Orange Pi remain user-side
acceptance checks, not claims of physical hardware testing by CI.

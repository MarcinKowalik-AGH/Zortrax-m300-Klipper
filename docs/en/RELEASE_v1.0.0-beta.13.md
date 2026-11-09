# v1.0.0-beta.13 — responsive read-only OLED mirror with complete animations

**Target:** Zortrax M300 Classic; Orange Pi host R16.12 / Fluidd 1.37.7.
Supersedes beta.12 without changing the MCU firmware, G-code procedures,
bed mesh, PC7 contact safety, heater control, the buzzer or OLED transport.

## Root causes addressed

The beta.12 viewer used only Moonraker's normal `notify_status_update`
subscription (~250 ms cadence), and replaced the entire PNG `img.src`
with each notification. This compounded normal Klipper rendering and
network delays. Browsers could also blank an animated icon region
temporarily when replacing an image whose next PNG was still decoding.

The revised viewer asks Moonraker for only the `m300_oled.oled_preview`
field using `printer.objects.query` on Fluidd's existing authorized
WebSocket. Queries are serial (never overlapping) and the next query is
sent only after the previous settles plus 85 ms. The query is passive;
it cannot change nozzle temperature, motor state, menu selection or MCU
OLED data. The existing 250ms subscription remains the initial fallback.
Direct query status is chosen when newer; out-of-order and disconnected
states are discarded. Polling stops while the widget is collapsed or the
browser is hidden.

The frontend now uses a **Canvas 256×64** and decodes the next frame
offscreen. Its current, fully painted pixels remain until the new frame
is ready. Late image completions are rejected using a generation token,
eliminating blank frames caused by asynchronous `img` replacement.

## Animation coverage and constraints

Host tests render complete pages containing the animated Klipper menu
logo and Home X Cartesian symbols through the actual `m300_oled._render`
pipeline. They assert the 50×50 icon exists in every animation phase.
This distinguishes missing image data at the source from a slow browser
presentation. The viewer retains all original 4bpp luminance values and
the half-width, centered 4:1 card layout.

The display shows host-rendered frames, which may lead the physical
OLED while the latter is transferring. Standard Klipper animation
periods (e.g., 500 ms) and its encoder input timing remain unchanged.
There is no physical OLED optical readback.

## Upgrade on an installed M300

When Klipper shows Ready and the printer is idle:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Hard-refresh Fluidd with Cmd+Shift+R. Do **not** flash the MCU.

## Validation

The release requires a complete STM32F103 build, **702 host tests**,
9 repository contracts, native Klippy FILEOUTPUT scenarios,
OLED/encoder/RLE/ACK/timeout recovery and homing/PC7/thermal/macro
regressions, frontend Vitest, TypeScript, strict ESLint, production Fluidd
build, versioned deployment manifests and checksum validation.
No automated test guarantees an end-to-end millisecond latency on every
Orange Pi, browser and LAN. Confirm visual parity and responsiveness
on the physical printer after installing.

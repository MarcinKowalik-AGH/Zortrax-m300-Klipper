# M300 Classic — MCU 1.0.2: original Zortrax startup logo

[Main guide](../../README.md) · [MCU 1.0.2 release and SD ZIP](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.2) · [Unified RC3 artwork](RELEASE_v1.0.0-rc.3.md)

## Startup sequence

After the existing bootloader hands control to the application, the MCU
initializes the OLED, displays the original **Zortrax** logo and then shows
**Waiting for Klipper...**. The complete logo stays visible for 2.5 seconds
unless the host takes display ownership sooner. Once connected, Klipper owns
the display. The firmware-update screen and bootloader are not changed.

![Original logo — actual MCU raster enlarged 3x](../assets/startup/zortrax_startup@3x.png)

This is a digital rendering of bytes emitted by the production MCU code in
a software model, not a photograph. The native logo is 160 × 40 pixels at
(48,12) on a 256 × 64 display, preserving the original four-bit luminance
levels. No replacement font, bitmap scaling, blur or threshold is used.
The documentation enlargement uses exact integer nearest-neighbor scaling.

## Original source

The artwork was recovered from the archived disassembly of Inventure
1.6.1/r0323: descriptor `0x0802C910`, compressed block `0x0802C924`. The
3200 decoded bytes match the independently archived original audit checksum:
`0082d29a88eef7515547189dedd83a7ef8b50fc32f0ab93ef307fb58439560d5`.
The original firmware used this placement and a 2500 ms waiting variant.
This port implements the hold without blocking communication or safety work.

The [canonical raster and provenance](../assets/startup/zortrax_logo_r0323.json)
retain source hashes. `ci/generate_startup_logo.py --check` verifies the asset
and generated ROM table. This remains attributed manufacturer artwork,
not newly authored project artwork.

## Host and fault preemption

A host display claim immediately cancels any startup phase. A quick host
connection can shorten or skip the logo; presentation must not delay the
Klipper handshake. Critical shutdown blanks the obsolete screen immediately,
then the existing bounded task draws the fault screen. During the static
logo hold, noncritical error metadata is checked at intervals of at most
100 ms. Releasing host ownership, losing the link or clearing an error
never replays the startup logo.

The existing 128-byte scanline buffer is retained. The original bitmap uses
3200 bytes of read-only flash and needs no additional full-screen RAM buffer.
Every task iteration still sends at most 32 SPI bytes. There is no busy-wait
or serial-command delay during the 2.5-second display hold.

## Installation on an already configured M300 Classic

Keep a known-good previous application. Finish printing; do not flash while
paused. Disable heater targets and allow the hotend to cool. Extract
`M300_MCU_v1.0.2_SD.zip` and copy only `M300APP.M3B` to the SD card root.
The archive is an application update, not an entire-flash image.

```bash
sudo systemctl stop klipper
```

Use the previously validated SD application-update procedure in the existing
M300 bootloader. Do not mass-erase flash, replace the bootloader or overwrite
factory data. After confirmed programming, remove the update file or card.

```bash
sudo systemctl start klipper
```

Read `ZORTRAX_MCU_STATUS`, `ZORTRAX_SETTINGS_STATUS` and `ZORTRAX_OLED_STATUS`.
Expected identity is MCU **1.0.2**, with host **1.0.0-rc.3**, Ready, fault 0
and matching **750000 baud**. There is no required host update solely for
this splash. Fluidd port 4480, unified icons, homing, bed mesh, PID, heaters,
independent cooling, qualified Z configuration and upstream Klipper stay
unchanged.

## Verification limits

Tests compare exact transmitted logo pixels at all eight supported UART
rates, inherited timer epochs, display timing, host claims and shutdown at
every startup phase. Recovery tests cover voluntary host release, lease
expiry and error metadata without replaying the logo. Build checks retain
Flash/RAM bounds and validate the M3B application at `0x08008000`.
CI does not flash or qualify a physical printer. Assess appearance during
normal startup; do not deliberately cause printer faults to view transitions.
The previously saved application can be restored using the same validated
SD bootloader procedure.

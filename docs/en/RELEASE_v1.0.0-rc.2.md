# M300 v1.0.0-rc.2 — exact legacy XY cleanup and host-update policy

[Main guide](../../README.md) · [RC1 controls](RC1_UI.md)

RC2 fixes the leftover TEST_ZORTRAX_XY reported on 12 November 2026. Its body
uses SPEED default 200, TEST_M300_XY_STATE and RESTORE_GCODE_STATE MOVE=0.
RC1 did not recognize its exact command hash and preserved it as a potentially
custom macro. This is an installer recognition omission, not a motion failure.
The new hash is 53be4a2ac5933a02df7321ed45f99ef9fe82d82b59faead042f1c472ecf3580f.
Only that known body is added to the existing allowlist. Different commands,
variables or parameters remain protected. Reference code is a test fixture,
not an active macro. Existing backups, exact rollback and config includes remain.

## Upgrade only while idle and Ready, never during a print or pause

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Hard-refresh Fluidd. The macro should be absent from the configfile status,
not merely toggled invisible. Qualified Z, mesh, PID, UART, motion, heating,
START/PAUSE/RESUME/CANCEL and the frontend remain unchanged. Firmware is still
`0.13.14.19-TONED-OLED-UART8`; do not flash `MCU/M300_SD.zip` for this update.
The 65 beta.20 illustrations remain historical, explicitly labeled evidence.

## Independent updates

The user's Moonraker change from 9e676eba6b02661a4dfa3ec6e7ac3f3504498e6d to
b559b9a81161f958a43c2f527b6ad96f73310d5d is one commit affecting only status
subscription filtering. The intersection of dictionary keys replaces a walk
through every subscription. No firmware, UART or API structure is changed.
This is a low-risk code-review assessment of that exact target, not a hardware
test or approval of future dev-channel changes. Back up configuration/database,
update Moonraker alone while idle and check reconnection. Reinstalling M300
is not required after updating Moonraker alone.
[Moonraker diff](https://github.com/Arksine/moonraker/compare/9e676eba6b02661a4dfa3ec6e7ac3f3504498e6d...b559b9a81161f958a43c2f527b6ad96f73310d5d).

Do not use Update All. The fourteen reported system packages include kernel,
DTB, U-Boot, BSP and device firmware. Temporarily hold that hardware group and
validate it separately with a recoverable SD-card image; this also postpones
security fixes, so the freeze is not a permanent security policy. Routine
userspace candidates still require APT simulation and dependency review.
linux-libc-dev is userspace interface headers, not the running kernel.
[Armbian update policy](https://docs.armbian.com/config/updates/).

The reduced output klipper {} alone proves neither update status nor absence
of local modifications. Keep the project-pinned Klipper and modified Fluidd;
use the M300 installer instead of independently upgrading arbitrary upstream
Klipper and assuming the port can be reapplied. RC2 itself does not hold or
upgrade system packages, edit Moonraker settings, change upstream Klipper or
alter boot configuration. Seven new regression cases exercise exact recognition,
root/include migration, formatting, custom preservation, rollback, idempotence,
SAVE_CONFIG, stale Fluidd preferences and the genuine RC1 version-module upgrade. No printer hardware tests were run.

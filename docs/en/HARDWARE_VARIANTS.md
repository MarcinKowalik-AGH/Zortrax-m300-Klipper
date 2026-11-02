# M300 hardware revision and Z profile

[Polski](../pl/HARDWARE_VARIANTS.md)

MCU R14.5 and host R16 read the retained factory hardware revision once at
Klippy identification and select the native Z scale before configuration and
board enable. There is no new polling, motion wrapper, GPIO/ADC owner or Flash
write. PID, extruder calibration, speed limits and saved configuration remain
in their existing files.

## Original firmware evidence

The M300 stock 1.3.1 application is 146392 bytes, based at 0x08008000, SHA-256
`11e2ea439d33436418bbeb51579cc7c12ef0a329019829bcf7e5eccbfc863b75`.
Direct ARM disassembly confirms the following chain, supplementing the archived
M07 stock contract:

| Location | Meaning |
|---|---|
| 0x0800A428 | Reads a factory record from 0x0803F800 + 24 × ID |
| 0x080181E0 | Requests ID 3, requires one payload byte, subtracts 0xE0 |
| 0x200015F0 | Stock runtime hardware revision byte |
| 0x08015FB0 | M300 profile initializer selects model family 4 |
| 0x08018930 / 0x080189C4 | Selects the M300 profile using the revision |
| 0x080242F4 + 68 | Older profile: float 800.0 Z steps/mm |
| 0x080243A4 + 68 | Newer profile: float 400.0 Z steps/mm |

The physical factory record header is at **0x0803F848**, payload at
**0x0803F84C**. A one-byte ID3 record has header **0xAABB0103** (little-endian
bytes 03 01 BB AA). Raw E4 means HW04; E5 means HW05.

| Decoded revision | OEM Z scale | Native rotation_distance, 200 full steps × 16 microsteps |
|---|---:|---:|
| Less than 5 | 800 steps/mm | 4 mm |
| At least 5 | 400 steps/mm | 8 mm |

This is the selector rule, not a list of every shipped M300 revision. An
application-only image does not contain this retained factory record. The
private backup examined for HW05 has raw E5; no serial, UID or full dump is
published. The official Marlin M300_v5 configuration also uses Z=400:
https://github.com/Zortrax3D/MarlinConfigurationsZortraxM200/blob/12b32a9a2eb69c070f69a6cb4dfbd1a3fa74da22/config/examples/Zortrax/M300_v5/Configuration.h

## Port behaviour

The MCU exposes read-only `m300_factory_query` and factory ABI 1. It returns the
raw header/byte and decoded revision/scale, including while unconfigured or
shut down. The host independently validates the record and decoded telemetry.
Only header 0xAABB0103 and payload E0..FE are accepted; FF/erased records,
wrong IDs, lengths and inconsistent telemetry never authorize an automatic
profile. This validation is stricter than blindly wrapping an invalid OEM byte.

The default `[m300_mcu] z_profile: factory` requires R14.5 factory ABI 1.
A valid record selects native stepper_z rotation distance using Klipper's
existing set_rotation_distance API during `klippy:mcu_identify`. Stock Z must
be local PB7, 16 microsteps, 200 full steps and have no gear ratio. Both the
M07 count arithmetic and motion configuration audit use that same scale.
No automatic physical qualification, homing or resumed operation is implied.
The legacy commissioning profile name remains accepted for compatibility;
its existing clearance, travel and thermal conditions remain unchanged.

Missing/invalid identity causes a descriptive startup error. For a replaced
screw or an intentionally configured machine, select explicitly:

~~~ini
[m300_mcu]
z_profile: config
~~~

This keeps the configured native Z scale and the configured M07 scale; the
identity is reported when supported but does not override them. The existing
M07 stock arithmetic supports 400 or 800 steps/mm. Factory mode does not rewrite
rotation_distance or stock_steps_per_mm in the file and does not add pending
SAVE_CONFIG values. Saving PID retains its normal native behaviour. The status
reports configured and effective rotation distances separately.

## Inspection and validation

Use `ZORTRAX_HARDWARE_STATUS` or the `hardware` field in `ZORTRAX_MCU_STATUS`.
OLED Information shows the revision, effective Z scale and selected mode;
Motion status uses the effective scale. Moonraker exposes the same information
under m300_mcu.hardware. Reconnect creates a fresh read; stale identity is not
reused. FILEOUTPUT explicitly reports FILEOUTPUT_NO_FACTORY_READ.

Public checks include 1792 C decoder cases, host malformed-record/override/
timeout/startup tests, and real pinned Klippy FILEOUTPUT processes with
synthetic HW04/HW05 records. A native 1 mm planned Z move yields respectively
800/400 steps in the native solver, and M07 uses the matching scale. An erased
record is rejected before MCU configuration. These are software checks, not
measurements on either physical printer. First physical validation must confirm
the reported revision and measured Z distance; full travel remains separate.

R16 uses normal native G28/probe and removes the legacy commissioning motion
configuration from normal operation. Factory selection and the explicit config
override above are unchanged. See FEATURES.md.

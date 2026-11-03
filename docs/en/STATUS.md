# Current status — R16.7 test release

MCU R14.5 remains unchanged. Host R16.7 and current documentation are English
only. The pinned upstream remains ee2c6fb6b00b2b5d097ef70d0868df7d74943b51.

Maintenance now includes Fan test with Back, Toggle upper fan and Toggle
lower fan. It uses the recovered save/off/0–150/restore flow and original
font/layout. The upper native thermostat remains a floor; its Cooling state
is shown consistently on OLED and Fluidd. Four new macros share that owner.
Heat and platform actions also expose the same English procedure identity
and messages, without interrupting the acknowledged physical hold row.

Software validation passes 258 host tests, 9 repository contracts, 17 check
groups and 13 actual Klippy FILEOUTPUT cases. Independent original-firmware
runs cover three fan sessions, two Heat branches, fifteen platform-selection
cases and twelve complete fan-menu frames. The previous M07/material/Z
regressions, 110 dialog frames and 20,002 arithmetic vectors remain covered.

The audit fixed cursor reset after a fan toggle and loss of a fault reason
at shutdown. It also reduced fan status reads from six cached MCU snapshots
to one. Host-only latency measurements and their limits are in the report.
No Orange Pi, UART, electrical duty, airflow or physical movement measurement
was performed in this iteration.

Calibration, factory Z scale, PID/E, sensor includes, geometry and general
motion limits retain their existing owners and upgrade rules. Full legacy
M02/Z-code printing remains disabled. The installer accepts known earlier
versions and provides exact rollback; physical acceptance remains pending.

See [validation and performance](VALIDATION_R16_7.md),
[menu/macro bindings](MAINTENANCE_MATERIAL.md) and [installation](INSTALL.md).

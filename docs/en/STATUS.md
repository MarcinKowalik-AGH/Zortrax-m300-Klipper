# Current status — R16.6 test release

MCU: R14.5, unchanged. Host: R16.6, English only. Upstream:
`ee2c6fb6b00b2b5d097ef70d0868df7d74943b51`.

The previous completion statement did not substitute for procedure validation.
This iteration re-executes OEM 1.3.1 control flow and corrects confirmed gaps:
Unload confirmation order, M07 Y-before-X and session offsets, ordinary
five-update Z reference, native paused Change, M07/native-print exclusion,
result return navigation, and runtime language consistency.

Implemented and software-tested: the two requested OEM submenus, shared
OLED/Fluidd dialogs, seven procedure macros, bounded native motion/contact
ownership, 260/258 and 240/238 thresholds, calibrated material transport,
pause preservation and explicit Resume, error/cancel handling, exact command
restoration and reversible migration.

Validation: 233 host tests, 9 repository contracts, MCU/register/startup
checks and 13 real Klippy FILEOUTPUT cases. Source evidence adds 5 executed
material traces, 3 wizard traces, 2 five-contact Z profiles, 6 XY-offset seeds,
110 renderer frames and 20,002 screw-turn vectors. Only modeled boundaries
are covered by the procedure tests; there is no new physical UART/printer run.

Status polling no longer copies a complete material transport plan. M07 and
ordinary Z share the same bounded native probe capability and rounding policy.
The obsolete post-retract WAIT_REMOVE path has been removed.

Native PID, sensors, factory Z scale, calibrated E, deliberate axis bounds,
normal velocity/acceleration controls, OLED transport/refresh, sleep notice,
MCU cooling and connection lifecycle remain under their existing owners.
The legacy full OEM M02/Z-code print engine remains separately disabled.

See [complete validation and acceptance](VALIDATION_R16_6.md),
[Maintenance / Material](MAINTENANCE_MATERIAL.md), [M07 / Z](LEVELING.md),
and [installation](INSTALL.md). Earlier printer photographs remain historical
on-device evidence; they do not establish physical acceptance of R16.6.

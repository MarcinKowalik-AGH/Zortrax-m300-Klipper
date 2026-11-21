# M300 Classic final audit — 21 November 2026

Final source release **1.0.0**, paired with **MCU 1.0.8**. Baseline:
RC34, commit `38e1c70e5ed7c974c709b9923613e22994832e57`.
[Detailed audit and procedure matrix (PL)](../pl/AUDYT_FINAL_2026-11-21.md).

The review follows each native procedure through its shared OLED, Fluidd and
console entry points, owner, finish, cancellation and error path. It compares
the current implementation with the October OEM A–D reconstruction and I/O
audit, the November configuration/error audits and the hardware register.
The older audits describe their dated baselines. Current runtime behavior and
version-specific operator evidence take precedence over obsolete port status.

## Finding and correction

On RC34, `M300_CHANGE TEMP=999` could request a service park before rejecting
the temperature. The material preflight also marked the protected pause as
requiring a change before validating every precondition. A rejected request
could therefore leave the print FAILED or prevent an otherwise valid Resume.

The shared `plan_request` now checks the plan, transport budget and both
temperatures before pause or park. The material owner changes pause flags only
after checking its live prerequisites and sensor. If readiness changes during
parking, rejection before acceptance preserves the paused print and its prior
resume permissions. A failure after acceptance keeps the existing heater-off
and fault handling. An earlier incomplete material change still has to finish
before the print can resume.

The tests cover active-print rejection without movement, invalid requests in
a settled pause, readiness and sensor rejection without pause mutation, a
readiness change during parking, and a failure after material acceptance.

## Procedure coverage and cleanup

The [current inventory](PROCEDURE_INVENTORY.md) covers homing, contact leveling,
25-point mesh, start/end, protected pause/resume, material transport, platform
movement, heating, fan test/PID, models/SD/Z-code/reprint, NVM/counters and
display/lifecycle behavior. Existing bounds, cancellation, queue drain,
identity checks and fault tests remain in the full regression suite.

Request planning has one implementation. Current guides and installation URLs
use 1.0.0. Historical audits are labeled, the obsolete Service / Tests inventory
row is replaced with the current diagnostics behavior, and final publication
supports the stable tag without marking it as a prerelease. Existing release
tags and assets remain immutable. No new hardware polling or step-path work
was added; no measured motion or UART speedup is claimed.

The host suite contains **989 tests**. Five additional publication tests execute
the actual script with modeled GitHub responses, including failed-build and
wrong-tag rejection. The release workflow also performs a fresh ARM build,
MCU register and Flash models, native Klippy FILEOUTPUT scenarios, installation
migration/rollback, Fluidd build/tests, documentation and package verification.
Exact results belong to the release commit's
[Actions run](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/actions/workflows/build-m300.yml).

The installer now recognizes the exact reviewed RC34 bytes of the three
changed runtime modules. A further host regression exercises that upgrade,
idempotence, exact rollback and rejection of a local modification. Migration
of the operator's `20261121-095908.zip` snapshot also preserved all 16 protected
sections and all 41116 bytes of SAVE_CONFIG, without duplicate sections.

## Hardware scope

No physical printer was operated during this audit. The
[hardware register](../pl/ACCEPTANCE_REGISTER.md) retains each observation's
original version and scope. Contact repeatability, first-layer coverage and
the complete final-version material/standby/flow-confirmation/resume sequence
still need operator confirmation. A final source version does not turn these
pending checks into hardware acceptance.

[Release and update](RELEASE_v1.0.0.md) · [Status](STATUS.md).

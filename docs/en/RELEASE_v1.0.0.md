# Zortrax M300 Classic 1.0.0 — 21 November 2026

Final source release: **host 1.0.0 + MCU 1.0.8**, with the project Fluidd on
port **4480**. This version supersedes RC34. See the
[final audit](FINAL_AUDIT_2026-11-21.md) for procedure coverage, source evidence
and the remaining hardware checks.

A rejected material-change request previously could mark an intact pause as
requiring a completed change. Through the operator macro, an invalid temperature
could also start parking and then fail the print preparation. All entry points
now validate the material plan and temperatures before requesting pause or park.
The material owner marks the change required only after its preflight succeeds.
If readiness changes during parking, a rejection before acceptance leaves the
print paused with its existing resume permissions. An accepted procedure that
fails still follows the original heater-off and fault path.

The release consolidates request validation, refreshes the current procedure
inventory and installation links, identifies older audits by their baseline,
and adds tests for final-version publication. The production catalogue retains
36 `M300_` operator macros; compatibility command aliases remain available.
MCU, contact algorithms, heater limits, cooling, UART and OLED transport are
unchanged. Software verification does not close the hardware acceptance ledger.
The installer recognizes the exact RC34 modules being replaced; locally edited
modules remain protected. Upgrade, idempotence and exact rollback are covered
by a new regression and by migration of the supplied configuration snapshot.

## Update

Finish the active operation, wait for Ready and turn both heater targets off.
In the existing `orange-pi` checkout:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

To update or repair the matching Fluidd build separately:

```bash
python3 install-orange-pi.py --update-fluidd --port 4480
```

Read `ZORTRAX_INFO REFRESH=0` afterward: host **1.0.0**, MCU **1.0.8**.
An already installed MCU 1.0.8 needs no reflash for this host correction.
If needed, extract `M300_SD.zip` from the full release, verify its checksums
and install `M300APP.M3B` through the existing compatible bootloader.

[First installation](FIRST_INSTALL.md) · [Update and rollback](INSTALL.md) ·
[Hardware acceptance](../pl/ACCEPTANCE_REGISTER.md).
The illustrated OLED catalogue retains its explicitly labeled beta.20 baseline.

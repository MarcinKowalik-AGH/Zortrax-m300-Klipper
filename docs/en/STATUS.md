# Release status and hardware acceptance

The current M300 Classic release candidate pairs Klipper host **1.0.0-rc.32** with **MCU 1.0.8**. Use `ZORTRAX_INFO REFRESH=0` to read both versions from a running printer. [Operator handbook](USER_GUIDE.md) · [Installation and update](INSTALL.md).

The operator reported a completed Benchy and separately observed bed lowering and head parking at print completion. A normal power cycle preserved the verified MCU print-time total on the tested RC19/MCU 1.0.6 combination. The 20 November screenshot shows an ongoing flow-test print, an OLED preview and an active named mesh. It does not identify the installed firmware version. The [hardware register](../pl/ACCEPTANCE_REGISTER.md) records each observation and the outstanding checks, including full RC32 manual purge and resume on hardware, contact repeatability and first-layer coverage.

## Historical SD and display changes

R16.11 reduces host file-write operations during SD import by batching up to
64 KiB. For a partial final sector, the host requests only the file bytes
after the MCU verifies the full sector CRC. R14.5 supports both changes with
its existing read-only SD commands.

R16.10 adds contextual PRINTING, PAUSE MENU and PRINTING DONE screens.
The OLED and Fluidd share native pause, resume, cancel and job state.
The configured SD reader and the Models menu support both G-code and the
audited Classic M300 Z-code subset. English is the only interface language.

Those tests used host R16.11 and MCU R14.5.

Classic M300 firmware 1.3.1 keeps its pause coordinates and feed rate in RAM.
Resume continues the open print session. The recovered pause flow has no SD
checkpoint or recovery after a restart.

[Print contexts](PRINT_CONTEXT.md) · [Procedure inventory](PROCEDURE_INVENTORY.md) · [Install](INSTALL.md)

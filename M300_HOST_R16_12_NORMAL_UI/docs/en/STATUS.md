# Current status — R16.11 test release

R16.11 reduces host file-write operations during SD import by batching up to
64 KiB. For a partial final sector, the host requests only the file bytes
after the MCU verifies the full sector CRC. R14.5 supports both changes with
its existing read-only SD commands.

R16.10 adds contextual PRINTING, PAUSE MENU and PRINTING DONE screens.
The OLED and Fluidd share native pause, resume, cancel and job state.
The configured SD reader and the Models menu support both G-code and the
audited Classic M300 Z-code subset. English is the only interface language.

The supported combination is MCU R14.5 and host R16.11. Physical OLED,
Fluidd browser and printer acceptance are pending.

Classic M300 firmware 1.3.1 keeps its pause coordinates and feed rate in RAM.
Resume continues the open print session. The recovered pause flow has no SD
checkpoint or recovery after a restart.

[Print contexts](PRINT_CONTEXT.md) · [Procedure inventory](PROCEDURE_INVENTORY.md) · [Install](INSTALL.md)

# Behaviour — R15.7

[Install](INSTALL.md)

| Condition | State | Display |
|---|---|---|
| Less than timeout since interaction | AWAKE | Current view, normal contrast |
| Timeout during work, pause, movement or heater target | DIM | Current live view, dim contrast |
| Timeout while idle | ENTERING_SLEEP | Original moon and Entering sleep mode |
| Notice acknowledged for notice_seconds | OFF | OLED emission disabled |
| Operator interaction | AWAKE | Refreshed current view |

The notice timer begins only after framebuffer and contrast acknowledgements.
A transport reinitialization restarts it. Work starting during the notice
restores the progress view at dim contrast. Work ending without new interaction
allows the notice and subsequent blanking.

Fresh knob events and external Moonraker G-code requests count as interaction.
Object polling, heartbeats, temperature updates and internally replayed
virtual_sdcard G-code do not. External automation using gcode/script also wakes
because that API does not identify it separately. Raw PTY input is not
intercepted; ZORTRAX_DISPLAY_WAKE is available.

The complete first invisible gesture is consumed, including hold and release.
It cannot choose an unseen action or grant a new encoder movement permission.
Release/STOP delivery to the existing owner remains. After notice cancellation,
actions remain guarded until the ordinary framebuffer is acknowledged.
A click on a visible dim view works normally.

## Shared transport

The existing OledStream/FastOledStream, token sequence, DMA window and UART
budget remain in use. C1 contrast and AE/AF changes wait for a frame boundary
and acknowledgements. Wake sends a current framebuffer before AF. OFF suppresses
hidden framebuffer traffic but retains input and the existing heartbeat.
SPI/UART rates, MCU timers and interrupt priorities are unchanged.

DMA updates compare the RLE blocks for the bounding rectangle and the dirty
tiles. The host chooses the lower estimated UART cost, including command and
OLED acknowledgement overhead, and sends the selected blocks. The final
acknowledgement commits the complete framebuffer as the next comparison base.

An ACK timeout follows the existing reset_required path; no automatic board
reset or actuator enable is added. Shutdown/disconnect leaves local display
ownership with the MCU. The policy timer runs once per second, or every 0.1 s
during the notice. No per-step or per-G-code hot-path hook is added.

## Native menu

Native heater commands, heaters off, M106 and relative menu moves are restored.
They run through the ordinary G-code mutex outside the ACK callback. A queued
action expires on navigation or shutdown. SAVE/RESTORE preserves parser mode
after native movement refusal.

The R15.5 ABI and separate X/Y/XY/Z homing remain. M11 now recognizes these
actions. Earlier stale material-view and checked-file identity protections are
retained. No older LAB movement/heater owner is reinstated.

## Display sleep versus machine sleep

The extension does not call ZORTRAX_SLEEP/ZORTRAX_WAKE, change heater targets,
motors, fans or position. An existing maintenance SLEEP/SLEEPING transition may
trigger the notice, but display wake only restores the image. It does not
resume an operation or restore a previous heater target.

## Factory Z selection

R15.7 selects the native Z scale once at startup from retained factory ID3.
M07, motion audit and OLED use that scale. Missing/corrupt identity is a startup
error; z_profile=config is an explicit operator override. See
[Hardware variants](HARDWARE_VARIANTS.md).

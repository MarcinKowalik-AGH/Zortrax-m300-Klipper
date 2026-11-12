# M300 Classic host update — RC1

This folder contains the verified M300 host overlay, production configuration,
installer and its developer regression tests. On Orange Pi prefer the top-level
install-orange-pi.py wrapper, run as the Klipper account only while idle and
Ready. It checks printer state, applies this package and updates Fluidd groups.
The default local endpoint is Fluidd port 4480; it is validated and persisted.

The internal install.py defaults to a read-only plan. --apply performs a checked
atomic update with a rollback receipt. Existing mesh, PID, UART, qualified Z
and user macros are preserved. Unknown runtime edits are refused. Stock lab
macros are retired only when their recognized bodies match, never by deleting
all names containing TEST. Developer tests remain under tests/ and legacy/.

Public controls include ZORTRAX_OLED_BRIGHTNESS and ZORTRAX_LED_BRIGHTNESS,
LEVEL=1..16. Without a value they open the same choice as the OLED Settings
menu. No new movement or heater authority is granted by these shortcuts.
M300_SD.zip is the compatible MCU image packaged separately; this host change
does not require flashing it. Consult docs/en/RC1_UI.md in the source repository
and the release's first-install instructions before working on a blank host.

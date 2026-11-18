# M300 Classic RC20 with MCU 1.0.7

Marcin Kowalik <mkowalik@agh.edu.pl>

Open Zortrax → Settings → OLED dim time or OLED sleep time. Both controls display minutes since the last operator activity. Turn to adjust the selected timer, press to save, or hold to go back. In Fluidd, OLED_TIMERS in Klipper and ZORTRAX_OLED_TIMERS in ZORTRAX M300 open both sliders. Choose Save to apply both values. The command equivalent is `ZORTRAX_OLED_TIMERS DIM=5 SLEEP=15`. Both values range from 1 through 60 and dimming must occur at or before sleep. During prints, pauses, heating or service operations, the display can dim. Sleep mode → Disabled keeps the display awake. The existing sleep notice and first-gesture wake protection apply.

A fresh configuration sets dimming to 5 minutes and sleep to 15 minutes. Upgrading preserves an existing m300_display.cfg. A file containing only the original timeout keeps that threshold for both phases until an operator saves new values.

Use the orange-pi checkout and check SHA256SUMS. Install the application from MCU/M300_SD.zip through the existing bootloader. When the printer is idle and Ready, run `python3 install-orange-pi.py` and install the matching two-slider frontend with `python3 install-orange-pi.py --update-fluidd --port 4480`. Older manual illustrations use beta.20. Read `ZORTRAX_DISPLAY_STATUS`: PENDING waits for a safe write window and SYNCED confirms the board returned the requested pair. Repeat after a power cycle for hardware acceptance.

Set `debug: True` in the existing `[m300_mcu]` section and reload Klipper to include verbose M300 hardware, Z probe and retract diagnostics. The default is False. Fault and safety reporting remains active in both modes. The OEM print-time banks are separate from display settings.

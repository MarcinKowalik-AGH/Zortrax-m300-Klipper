# M300 Classic RC21 · OLED dim and power-off deadlines

With Sleep mode enabled, both timers run from the last operator input on the panel or through Fluidd. The same deadlines apply in Ready, while heating, during a print and while paused. The alarm LED continues to indicate faults independently. The first turn or click of the knob wakes the screen and restores the current view. The following gesture operates the menu.

Use OLED_TIMERS or ZORTRAX_OLED_TIMERS in Fluidd, or select OLED dim time and OLED sleep time under Settings on the panel. Each accepts 1–60 minutes. For example, `ZORTRAX_OLED_TIMERS DIM=1 SLEEP=2` dims after one minute and turns the OLED off at two minutes. The moon fades before the second deadline when time permits. Equal values turn the screen off directly at the common deadline.

To upgrade RC20 with MCU 1.0.7, finish the print, open the orange-pi checkout and run `git pull --ff-only && sha256sum -c --quiet SHA256SUMS && python3 install-orange-pi.py`. This host update uses the existing MCU timer storage. Check its readback with `ZORTRAX_DISPLAY_STATUS`. For older MCU installations, MCU/M300_SD.zip contains the application. Optional `--update-fluidd --port 4480` installs the timer sliders on sites missing that frontend. Historical manual illustrations show beta.20.

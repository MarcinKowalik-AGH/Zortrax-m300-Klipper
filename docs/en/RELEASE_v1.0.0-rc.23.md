# M300 Classic RC23 · OLED timeout editors

Open **Settings → OLED dim time** to adjust dimming or **OLED sleep time** to set when the display switches off. Each editor shows a single segmented slider, minutes and an animated icon on the right. Turn the knob and press to save. Hold to leave the editor without saving. On return to the parent menu the highlight stays on the item that opened the screen.

![Dimming slider](../img/oled-timers-rc23/dim.png)
![Sleep slider](../img/oled-timers-rc23/sleep.png)

Both timers count from the last operator interaction in Ready, during printing and while paused. Each accepts 1–60 minutes. With a preferred DIM of 15, shortening SLEEP to 5 applies DIM 5. Extending SLEEP to 10 gives DIM 10. Extending SLEEP to 20 restores DIM 15. SLEEP can continue up to 60. An explicitly selected DIM replaces the old preference. At equal deadlines the screen switches off at the common time.

On the Orange Pi, run the following in your orange-pi checkout with the printer idle and Ready:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py &&
python3 install-orange-pi.py --update-fluidd --port 4480
```

Install the MCU 1.0.8 application from `MCU/M300_SD.zip` to store both the preferred DIM and SLEEP directly on the board. MCU 1.0.7 records the effective timers and the Orange Pi retains the preferred DIM. Use `ZORTRAX_DISPLAY_STATUS` to inspect synchronization and read-back. These images were rendered from RC23. Historical manual illustrations show beta.20.

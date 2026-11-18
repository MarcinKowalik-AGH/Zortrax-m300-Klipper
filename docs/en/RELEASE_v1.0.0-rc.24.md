# M300 Classic RC24 · OLED brightness and Fluidd reconnect

Turning the brightness knob below the first segment previously selected a hidden Back row and displayed the saved brightness. A saved value of eight looked like a jump from one segment to half the bar. The knob now stops at one. Press to save the visible value or hold to return to the selected row in Settings. The same lower bound applies to LED brightness and the DIM and SLEEP time editors.

Fluidd continues reconnecting when Moonraker takes longer to return. It verifies an unexpectedly silent WebSocket with a read-only server request. After the same printer reconnects, Fluidd refreshes the page, including when embedded in OrcaSlicer. Automatic reloads are limited to one per two minutes. Disconnecting dismisses obsolete procedure prompts. The interface retrieves the current printer state.

Run the following from your orange-pi checkout while the M300 is idle and Ready:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py &&
python3 install-orange-pi.py --update-fluidd --port 4480
```

Reopen Fluidd on port 4480 once after installation to load the updated client. The fix uses MCU 1.0.8. Upgrading from RC23 requires the host and Fluidd updates. First installations can use `MCU/M300_SD.zip`. Historical manual illustrations show beta.20.

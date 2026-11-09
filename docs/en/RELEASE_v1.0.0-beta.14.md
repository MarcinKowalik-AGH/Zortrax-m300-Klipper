# M300 Classic v1.0.0-beta.14 — fixed-height Fluidd OLED preview

This release is a small frontend-only layout correction to beta.13.
The OLED emulator remains directly below the Temperature chart in
Fluidd. Its displayed dimensions are now fixed at **344 × 86 CSS px**
(precisely 4:1, corresponding to native 256 × 64).
In the original desktop screenshot this is about half the available
temperature-card width.

Resizing the Fluidd browser window or rearranging dashboard columns
no longer scales the preview vertically. When the column is narrower
than 344 px, a horizontal scrollbar shows the fixed-size display rather
than distorting or shrinking it. The offline placeholder has the same
fixed dimensions.

The update does not change the canvas backing store, the complete
animated Klipper icons, frame timing, WebSocket subscriptions/queries,
encoder controls, Moonraker, Klipper, host-based PNG generator,
OLED RLE/ACK/DMA/SPI/UART, MCU firmware, or any printer safety logic.

### Update existing Orange Pi

Only when the printer is idle and Klipper is Ready:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Then hard-refresh Fluidd (Cmd+Shift+R on macOS). No MCU flash is needed.

### Verification

Nine strict repository contracts include assertions for the
**344 px width, 86 px height, no fluid 50%/auto scaling, and
horizontal scrolling**. The complete GitHub Actions run validates
702 unchanged host regression tests, native Klippy FILEOUTPUT, original
MCU/transport compilation, frontend Vitest, ESLint, TypeScript,
production Fluidd build and the versioned deployment bundle.
Browser visual acceptance should still be checked after updating.

# M300 Classic v1.0.0-beta.17 — pipelined navigation and square OLED pixels

Supersedes beta.16. Frontend revision: `NAV-PIPELINE-2`.
The host event API remains `NAV-EVENT-1`. Host/MCU sources, animation cadence,
normal Klipper/Fluidd status cadence, UART/SPI/RLE/ACK and print procedures are
unchanged, including the beta.15 PAUSE/CANCEL, four-line purge and saved mesh.

## Navigation reception no longer waits for PNG decoding

The browser re-arms its single navigation event wait immediately after receiving
a new view. PNG decoding and canvas painting proceed independently. The decoder
holds at most one active image and one replaceable latest image; it never queues
all intermediate menu positions. A superseded decode cannot repaint an old row.
Hide, disconnect, reconnect and destruction invalidate pending images. Repainting
a decoded image after a DPI change does not fetch or decode another PNG.
This specifically improves bursts of quick knob movements; single-event and
physical knob-to-browser latency still require measurement on the printer.

## Device-pixel-exact rendering

The 256 x 64 OLED content is expanded into equal integer N x N device-pixel
blocks, with interpolation disabled. N is selected near the previous 344 CSS px
width using the current devicePixelRatio. Page zoom, monitor DPI changes and
layout changes recalculate the canvas and align its origin to the pixel grid.
A two-device-pixel dark guard surrounds the native image so compositor edge
antialiasing stays outside the actual OLED pixels. The native image retains 4:1.

**This replaces an exactly fixed 344 x 86 CSS size.** At DPR 1 the OLED content
is 256 x 64 CSS px; at DPR 2 it is 384 x 96 CSS px (768 x 192 device pixels).
There is also the small guard border. Width and height change together in steps
as page zoom changes. Narrow dashboard columns scroll horizontally instead of
stretching the canvas. Changing only the column width does not shrink the image.

The guarantee is about integer raster mapping in the application and the tested
browser screenshots. It cannot cover an OS magnifier, remote-desktop scaling,
external screenshots resized by another program, arbitrary CSS transforms added
by extensions, or a browser's temporary pinch-zoom compositor animation.

## Update

With the printer **idle and Ready**:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Hard-refresh Fluidd with **Cmd+Shift+R**. No MCU flash or Moonraker configuration
change is required. The runtime host payload is byte-identical to beta.16, so
existing upgrade protections and all print/motion safeguards remain intact.
The preview element reports `data-preview-revision="NAV-PIPELINE-2"` and its
integer `data-pixel-scale`. `ZORTRAX_OLED_STATUS` still reports `NAV-EVENT-1`;
that is expected because the host API did not change.

## Required validation

CI runs all 741 host regressions, native Klippy FILEOUTPUT, event API checks,
ARM build, frontend unit/component tests, ESLint, TypeScript, production Fluidd
and release integrity checks. New frontend tests cover reception during a slow
paint, a 1000-update burst with bounded decoding, late callbacks after teardown,
DPI changes, pixel geometry and unchanged periodic preview timing.

`REPORTS/OLED_PIXELS.json` compares EVERY native image pixel in actual Chromium
and Firefox screenshots at 15 renderer DPI values and two fractional column
widths (60 cases). Real renderer DPI is used: CDP device-scale emulation alone
can post-scale screenshots without changing the underlying pixel grid.
These are software/browser tests, not measurements on the physical M300 or
proof of any particular millisecond improvement. Publication requires a full
successful matching CI run and the verified orange-pi deployment.

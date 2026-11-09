# M300 Classic v1.0.0-beta.16 — immediate menu-selection preview

Supersedes beta.15. Preview API revision: `NAV-EVENT-1`.

## Scope

This release targets the delay between turning the physical encoder and seeing
its selected menu row in Fluidd. It does **not** increase icon-animation FPS or
change the physical display, MCU firmware, UART, SPI, RLE, ACK handling, print
procedures, thermal guards, or the fixed 344 x 86 CSS pixel preview size.
All beta.15 PAUSE/CANCEL and four-line START fixes remain included.

## Event-driven navigation

After the normal host renderer completes a changed menu view, a passive
observer wakes the preview's dedicated `m300/oled_preview/wait` endpoint.
Fluidd keeps one asynchronous wait request outstanding through its existing,
authorized Moonraker WebSocket. The request completes on a navigation event;
it does not enter `objects/query` or its 250 ms refresh timer and is not held
in Fluidd's ordinary status-notification cache. No extra service, port,
Moonraker component, proxy configuration, or authentication exception is needed.

This is an event-driven long wait, not another short-interval polling loop.
An unchanged wait returns after 10 seconds only to bound resource lifetime.
The next wait is armed immediately after the browser has processed the image.
During a quick first-to-last scroll, only the latest view is retained between
requests; obsolete intermediate images are not replayed. A single detent is
not delayed until the user stops turning the knob. Encoder/click processing
and all physical-action consent checks are unchanged.

Ordinary icon/temperature animations retain the previous status-query path
and cadence. A navigation response bypasses the preview's 125 ms image cache
limit, but uses the exact same already-rendered PNG pixels. Image sequence
numbers and session epochs prevent an older periodic response or a previous
Klippy session from restoring an obsolete menu selection. Late PNG decoding
cannot repaint an older image. Hidden/collapsed widgets cancel their own wait;
reconnection starts with a new client generation. There are at most eight
outstanding navigation waits on the host. If the optional event route is
unavailable, the existing periodic preview remains available.

The earlier beta.13 description overstated the effect of querying every
85 ms: those queries still used Klipper's shared status refresh. This release
uses a separate endpoint specifically to remove that wait for navigation.

## Update

With the printer **idle and Ready**, update the verified deployment:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Hard-refresh Fluidd with **Cmd+Shift+R** on macOS. No MCU flash is required.
The unchanged safe-upgrade list already contains the verified beta.15 OLED
module hashes. Unknown local edits are still refused rather than overwritten.

`ZORTRAX_OLED_STATUS` now includes `oled_preview.navigation_api: NAV-EVENT-1`,
`navigation_waiters`, and `navigation_delivered`. With an open visible preview,
turning the knob should increase `navigation_delivered`. The preview section's
HTML `data-navigation` attribute is `event` while the event client is operating
and `fallback` when only the ordinary path is active. This is a diagnostic,
not a new visual control. Print-control revision remains the beta.15 revision.

## Validation

The full host suite contains **741 tests**, including 20 new navigation,
backpressure, cancellation, stale-state, renderer-invariance and upgrade checks.
A separate check uses the **actual pinned Klipper reactor and WebRequest parser**
for a single detent, a first-to-last burst, and cancellation of a hidden widget.
Its report is `REPORTS/OLED_NAVIGATION.json` in the verified package. Any times
reported there are host event-to-reply times in the test environment, **not**
measured physical-knob-to-browser latency.

Frontend checks include immediate delivery without a polling delay, one
outstanding request, slow-browser backpressure, stop/reconnect generations,
malformed data, old session counters, delayed PNG decoding, collapsed widgets,
and unchanged canvas dimensions. CI also requires the existing TypeScript,
ESLint, production Fluidd, MCU ARM, native Klippy FILEOUTPUT, and package checksum
checks. The same full build now runs for pull requests before deployment.

No physical printer or user's browser is operated by CI. The first acceptance
check after installation is: one quick detent, a first-to-last scroll, stop on
the final row, then rotate-and-click. Check it both idle and during a short
supervised print; animation appearance should remain unchanged.

# Settings and Information

Open **Zortrax M300 → Settings** on the OLED or run `ZORTRAX_SETTINGS` in
Fluidd. Both surfaces use the same English labels, saved choices and action
handlers. The `<` mark identifies the current choice on list pages.
Brightness uses two independent 16-segment controls. Turn the encoder to
adjust and press to save. Hold to go back. In the M300 build of Fluidd,
drag the segmented control and release to apply.
Both bars follow the open OLED control through the existing Moonraker status
subscription. Turning the knob is a shared preview; press the knob or Fluidd's
Save button to store it. Releasing a dragged Fluidd slider also saves it and
updates the open OLED cursor. A remote change invalidates old physical click
receipts. Back remains valid after saving; leaving and reopening a dialog,
restart and shutdown still expire the old view. Reading the preview writes
neither NVM nor UART commands.

In Fluidd, the setting macros open button dialogs when called without
arguments. Explicit console arguments such as `ZORTRAX_LIGHT MODE=WHITE`
still apply the selected value directly.

Back from Settings or Information opens the Zortrax M300 menu in Fluidd.
Back again opens the main menu with Klipper and Zortrax M300. The main menu's
Back button closes the dialog and returns to the underlying Fluidd view.
The Klipper page shows print state. Motion, temperature and print controls
are on the Fluidd dashboard.

Help includes **Errors**: current identity and repair advice,
acknowledgement of nonfatal notices, and a read-only catalogue of the 21
Classic M300 OEM codes. The same codes and icons are available in Fluidd,
the live OLED and the R14.18 MCU-local shutdown screen. See [error handling](ERRORS.md)
for source bindings and the distinction between an available message and a
qualified hardware detector. Acknowledgement never clears a safety latch.

| Settings page | Choices | Fluidd access |
|---|---|---|
| Light | Dynamic, White, Disabled | `ZORTRAX_LIGHT MODE=DYNAMIC`, `WHITE` or `DISABLED` |
| Buzzer | Enabled, Disabled | `ZORTRAX_BUZZER STATE=ENABLED` or `DISABLED` |
| Sleep mode | Enabled, Disabled | `ZORTRAX_SLEEP_MODE STATE=ENABLED` or `DISABLED` |
| Language | English | `ZORTRAX_LANGUAGE` |
| Models sorting | Date, Name, Case-sensitive name, File size | `ZORTRAX_MODELS_SORT MODE=DATE`, `NAME`, `NAME_CASE` or `SIZE` |
| Full platform preheating | Enabled, Disabled | `ZORTRAX_FULL_PLATFORM_PREHEAT STATE=ENABLED` or `DISABLED` |
| OLED brightness | 1–16 | `ZORTRAX_SETTINGS` → OLED brightness |
| LED brightness | 1–16 | `ZORTRAX_SETTINGS` → LED brightness |

The existing host NVM saves choices. Selecting the active value avoids a disk
write. Disabled Buzzer also ends an active host beep. Dynamic Light follows the
printer through one state policy, independently of the open OLED or Fluidd menu:

| Printer state | Dynamic LED color |
|---|---|
| Ready, including passive cooling after a completed procedure | Green |
| Nozzle/bed heating, homing preheat or thermal test/PID heating | Red |
| Pause, pausing or resuming; includes material heating while paused | Purple |
| Printing and other active procedures once temperature is ready | White |
| Failed procedure, native print error or MCU shutdown | Red → green → blue, five seconds per color, repeated |

Priority is error, pause, heating, active work, Ready. A manual temperature
target remains red when no print or other procedure is active. Opening a menu
does not change this state. Homing, OEM leveling, the 25-point pad mesh,
material handling and fan tests all use the same observer. Normal fixed White,
Disabled and sleep-light choices remain available; an error overrides them.
The host alarm retains the selected LED brightness and restarts at red only
after the preceding error has cleared. It sends pin updates only on a color or
brightness change. No status-color UART polling or new heating/motion owner
is introduced. `ZORTRAX_MAINTENANCE_STATUS` includes `status_led` revision
`0.13.16.21-STATUS-LED`, the last applied RGB and alarm timing.

MCU R14.17 repeats the error sequence locally at full brightness after shutdown,
including host loss while the MCU guard is armed. It uses the permanent task
wake, so shutdown's removal of user timers cannot stop the sequence. Queued
generic GPIO/default writes cannot overwrite it. It neither clears the latch
nor changes heater, motor, fan or 50/45 C thermostat policy. This offline part
requires the R14.17 MCU application; the other shared colors are host changes.

LED brightness applies to both Dynamic and White. The two brightness settings
are independent and default to level 16 on existing installations.
Each OLED brightness control has one compact 16-segment bar at x16–173 and
a static display/lamp symbol at x200–249. The empty gap prevents overlap;
the icon's demonstration meter is hidden on the actual control screen.
Turn the knob on an active leveling screen to open Settings. Back returns
to the wizard. Fluidd brightness controls appear on their dedicated Settings
pages. Brightness, light mode and buzzer can change while a service owns
motion or heaters. The host saves these changes when the service releases
its resources.

Sleep mode gates the existing dim, moon notice, display off and encoder wake
sequence. Its timeout, notice duration and contrast come from
`m300_display.cfg`. Enabled dims the display during print inactivity and
restores the selected brightness on an encoder press. When idle, the moon
fades over the configured notice duration before the screen turns off.
Disabled keeps the OLED awake. A wake gesture from an off screen or moon
notice is consumed. `ZORTRAX_DISPLAY_STATUS` reports the applied contrast,
selected brightness and configured timing.

Model directories come first. Date and File size order entries newest and
largest first. Name uses case-insensitive comparison with a stable spelling
tie-breaker. Case-sensitive name compares the stored spelling. Change the sort
mode, then reopen Models to get a new listing.

Open **Zortrax M300 → Information** or run `ZORTRAX_INFORMATION` in Fluidd.

| Page | Displayed data |
|---|---|
| Firmware version | Host release, MCU release, pinned Klipper revision and OEM reference |
| Printer information | Model, hardware version, serial number and total printing time on one screen |
| Help | Project repository for documentation and issues |

MCU R14.6 exposes `M300_FACTORY_INFO_ABI=1`. It reads the factory serial
from ID1 and the last complete ID0 print-time record from the active OEM NVM bank.
The lifetime display adds the OEM minutes and the completed-job seconds
stored in the Klipper host NVM. A native Fluidd or Models print contributes
Klipper's `print_duration` at successful EOF. The legacy workflow retains
its own completion hook. Both use the same durable host counter.

On older MCU firmware, a configured `serial_number:` is a fallback.
An unavailable OEM counter is shown as unavailable. `ZORTRAX_INFO` also
reports the OEM and Klipper components separately.

Opening Information or Printer information requests Moonraker history in the
background. Fluidd's Printer information page has a Refresh button. In the console,
`ZORTRAX_INFO REFRESH=0` reads the current cache and `ZORTRAX_INFO REFRESH=1`
requests an update. The default endpoint is the local Moonraker server on
port 7125 and can be set with `moonraker_url:` in `[m300_settings]`.
Moonraker's history total is reported separately as `history_print_seconds`.
Earlier native prints from before host counter collection are not backfilled.

OLED Help shows the project address across three rows. Fluidd Help shows the
complete address. [Project GitHub](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper)

Full platform preheating is a persistent next-start choice. The shared G-code/Z-code start captures it once; enabling it adds `platform_soak_seconds` (60 seconds by default) of continuous temperature stability before homing. It never heats by itself, changes an active session or lifts the existing heater/motion limits.

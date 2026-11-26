# Settings and Information

> 1.0.4 controls: [current OLED/macro reference](RC1_UI.md). The [65-screen illustrated guide](../pl/OLED_FUNCTIONS.md) retains explicitly historical beta.20 renders. Implementation history and raw ABI identities below remain evidence, not RC display labels.

OLED menu button audio has two fixed pulse lengths: normal entry and other
selection/exit clicks are 35 ms, while an explicitly visible **Back** or
**Up** row produces a 140 ms pulse. A dedicated, bounded buzzer-off timer
controls the ending of each pulse independently of the 500 ms native
status/LED refresh; no motor, heater or encoder polling is added.
The saved Buzzer Disabled option immediately silences an active pulse and
prevents future menu clicks from sounding. Stale/unrecognized Back action
receipts are not allowed to produce the long confirmation.


Open **Zortrax M300 → Settings** on the OLED or run `M300_SETTINGS` in
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

RC1 adds direct `M300_OLED_BRIGHTNESS LEVEL=8` and
`M300_LED_BRIGHTNESS LEVEL=8` shortcuts. Omit LEVEL to open the shared
control. Only integers 1..16 are accepted; no rounding or separate settings store.

In Fluidd, the setting macros open button dialogs when called without
arguments. Explicit console arguments such as `M300_LIGHT MODE=WHITE`
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
| Light | Dynamic, White, Disabled | `M300_LIGHT MODE=DYNAMIC`, `WHITE` or `DISABLED` |
| Buzzer | Enabled, Disabled | `M300_BUZZER STATE=ENABLED` or `DISABLED` |
| Sleep mode | Enabled, Disabled | `M300_SLEEP_MODE STATE=ENABLED` or `DISABLED` |
| Language | English | `M300_LANGUAGE` |
| Models sorting | Date, Name, Case-sensitive name, File size | `M300_MODELS_SORT MODE=DATE`, `NAME`, `NAME_CASE` or `SIZE` |
| Full platform preheating | Enabled, Disabled | `M300_FULL_PLATFORM_PREHEAT STATE=ENABLED` or `DISABLED` |
| OLED dim time / OLED sleep time | 1–60 minutes each | `M300_OLED_TIMERS` |
| OLED brightness | 1–16 | `M300_SETTINGS` → OLED brightness |
| LED brightness | 1–16 | `M300_SETTINGS` → LED brightness |

The existing host NVM saves choices. Selecting the active value avoids a disk
write. Disabled Buzzer also ends an active host beep. Dynamic Light follows the
printer through one state policy, independently of the open OLED or Fluidd menu:

| Printer state | Dynamic LED color |
|---|---|
| Ready, including passive cooling after a completed procedure | Green |
| Nozzle/bed heating, homing preheat or thermal test/PID heating | Red |
| Pause, pausing or resuming; includes material heating while paused | Purple |
| Active SD print after completing `START_PRINT`, including changes in heater targets | Steady white |
| Other active procedures once temperature is ready | White |
| Failed procedure, native print error or MCU shutdown | Red → green → blue, five seconds per color, repeated |

Priority is error, operator pause, active printing after `START_PRINT`,
heating, other active work and Ready. A manual temperature target remains red when the printer is
waiting to heat outside active model printing. Opening a menu
does not change this state. Homing, OEM leveling, the 25-point pad mesh,
material handling and fan tests all use the same observer. Normal fixed White,
Disabled and sleep-light choices remain available; an error overrides them.
The host alarm retains the selected LED brightness and restarts at red only
after the preceding error has cleared. It sends pin updates only on a color or
brightness change. No status-color UART polling or new heating/motion owner
is introduced. `ZORTRAX_MAINTENANCE_STATUS` includes `status_led` revision
`0.13.16.21-STATUS-LED`, the last applied RGB and alarm timing.
For a red indicator, compare `status_led.state` with `ZORTRAX_ERROR_STATUS`
to distinguish heating from a fault signal.

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

Enable Sleep mode for automatic OLED dimming and power-off. Set both times
in minutes since the last operator interaction with the OLED_TIMERS sliders.
The allowed range is 1–60 minutes, with DIM at or before SLEEP. Ready, printing
and pause use the same deadlines. SLEEP temporarily caps the effective DIM. Increasing SLEEP restores the preferred DIM up to the new deadline. Both times are measured from the same last interaction. The moon fades before SLEEP when time permits.
At SLEEP the panel switches off. The first encoder gesture wakes it and
restores the selected brightness. Disabled keeps the display awake.
The alarm LED operates independently. `ZORTRAX_DISPLAY_STATUS` reports the
configured times, MCU readback and display state.

Model directories come first. Date and File size order entries newest and
largest first. Name uses case-insensitive comparison with a stable spelling
tie-breaker. Case-sensitive name compares the stored spelling. Change the sort
mode, then reopen Models to get a new listing.

Open **Zortrax M300 → Information** or run `M300_INFORMATION` in Fluidd.

| Page | Displayed data |
|---|---|
| Firmware version | Host release, MCU release, pinned Klipper revision and OEM reference |
| Printer information | Model, hardware version, serial number and total printing time on one screen |
| Help | Project repository for documentation and issues |

The factory information ABI reads the serial from ID1 and print minutes
from ID0 in the active OEM settings bank. RC8 also records model-print time
from completed, cancelled and interrupted native Fluidd and Models jobs
in a durable host counter. The lifetime display adds the factory minutes
and the host seconds still pending transfer. The host retains seconds below
one minute and reconciles confirmed transfers so they count once.

On older MCU firmware, a configured `serial_number:` is a fallback.
An unavailable OEM counter is shown as unavailable. `ZORTRAX_INFO` also
reports the OEM and Klipper components separately. With MCU 1.0.8 the host transfers whole minutes automatically once the printer is idle and the MCU accepts a write. Use `ZORTRAX_HARDWARE_STATUS` for the active bank, pending state and any wait reason. [Counter readback and persistence](MCU_FIRMWARE_1.0.8.md#read-the-counter).

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

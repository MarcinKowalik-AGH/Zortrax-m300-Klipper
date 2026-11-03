# Settings and Information

Open **Zortrax M300 → Settings** on the OLED or run `ZORTRAX_SETTINGS` in
Fluidd. Both surfaces use the same English labels, saved choices and action
handlers. The `<` mark identifies the current choice. The encoder scrolls
through the available rows.

In Fluidd, the setting macros open button dialogs when called without
arguments. Explicit console arguments such as `ZORTRAX_LIGHT MODE=WHITE`
still apply the selected value directly.

| Settings page | Choices | Fluidd macro |
|---|---|---|
| Light | Dynamic, White, Disabled | `ZORTRAX_LIGHT MODE=DYNAMIC`, `WHITE` or `DISABLED` |
| Buzzer | Enabled, Disabled | `ZORTRAX_BUZZER STATE=ENABLED` or `DISABLED` |
| Sleep mode | Enabled, Disabled | `ZORTRAX_SLEEP_MODE STATE=ENABLED` or `DISABLED` |
| Language | English | `ZORTRAX_LANGUAGE` |
| Models sorting | Date, Name, Case-sensitive name, File size | `ZORTRAX_MODELS_SORT MODE=DATE`, `NAME`, `NAME_CASE` or `SIZE` |

The existing host NVM saves choices. Selecting the active value avoids a disk
write. Disabled Buzzer also ends an active host beep. Dynamic Light follows the
printer, including native printing, pause and faults.

Sleep mode gates the existing dim, moon notice, display off and encoder wake
sequence. Its timeout, notice duration and contrast come from
`m300_display.cfg`. Enabled uses that configuration. Disabled keeps the OLED
awake. The first wake gesture is consumed when the existing display policy
requires it. `ZORTRAX_DISPLAY_STATUS` reports the live state and configured
timing.

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

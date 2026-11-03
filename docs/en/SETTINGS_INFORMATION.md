# Settings and Information

Open **Zortrax M300 → Settings** on the OLED or run `ZORTRAX_SETTINGS` in
Fluidd. Both surfaces use the same English labels, saved choices and action
handlers. The `<` mark identifies the current choice. The encoder scrolls
through the available rows.

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
| Printer information → Printer model | Zortrax M300 Classic |
| Printer information → Hardware version | Reported factory profile such as HW05 |
| Printer information → Serial number | Available factory serial or explicitly configured printer serial |
| Printer information → Total printing time | Recorded Moonraker print history |
| Help | Project repository for documentation and issues |

The R14.5 protocol exposes the factory hardware record. With that MCU the
serial page shows **Unavailable** unless the operator enters the actual
printer serial as `serial_number:` in the existing `[m300_settings]` section.
The host identity is a separate value.

Opening Information requests Moonraker history in the background. Fluidd's
Total printing time page has a Refresh button. In the console,
`ZORTRAX_INFO REFRESH=0` reads the current cache and `ZORTRAX_INFO REFRESH=1`
requests an update. The default endpoint is the local Moonraker server on
port 7125 and can be set with `moonraker_url:` in `[m300_settings]`.
The [Moonraker history API](https://moonraker.readthedocs.io/en/latest/external_api/history/)
provides recorded print time. It covers the jobs in that Moonraker database.
The view identifies missing history and cached totals after a failed refresh.

OLED Help shows the project address across three rows. Fluidd Help shows the
complete address. [Project GitHub](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper)

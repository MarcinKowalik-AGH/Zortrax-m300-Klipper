# M300 Classic host update

On an existing M300 Classic Klipper installation, run the top-level
`python3 install-orange-pi.py` as the Klipper account while idle and Ready.
For a separate Fluidd repair, run
`python3 install-orange-pi.py --update-fluidd --port 4480`.

`install.py` is the lower-level host updater. It defaults to a read-only plan
and provides a receipt for rollback. It preserves qualified Z, mesh, PID,
UART and user macros. Recognized historical macros are migrated only when
their bodies match the stock templates.

Use the top-level installation guide for your language. For the compact
`orange-pi` checkout, use the release-specific link in its top-level README.
The MCU application on `M300_SD.zip` is installed separately from the host.

# No nozzle contact during homing or bed measurement

Host R16.15, 26 November 2026. Existing MCU firmware 1.0.9 is sufficient.

A recognized missing or unstable PC7 contact aborts measurement and turns off
the heater targets. With a known native Z position, the host lowers the bed
by **100 mm**, at no more than 5 mm/s, clipped to the configured Z maximum.
It performs no XY travel or new approach. The bed stays lowered until the
next homing command.

The failed Z reference is invalidated and the operator receives:
`No contact - please clean nozzle and pad contacts, then repeat homing.`
The failed mesh is not saved. Clean the nozzle and contact pads, acknowledge
the error notice if necessary, then repeat homing and measurement. This
contact outcome does not require `FIRMWARE_RESTART`.

If the first coarse home did not establish Z, no further movement is attempted
in an unreferenced frame. A PC7 input that remains closed after lowering the
bed also requires checking the contact wiring. MCU, communication and motion
failures retain their protective shutdown behavior; no cleaning drop follows
a shutdown.

## Updating an existing host

Run while idle with heater targets off:

```bash
cd "$HOME/m300-orange-pi" &&
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
backup_dir="$HOME/m300-contact-backup-$(date +%Y%m%d-%H%M%S)" &&
mkdir -p "$backup_dir" &&
cp -p "$HOME/klipper/klippy/extras/"{m300_native_probe.py,m300_native_motion.py,m300_pad_mesh.py} "$backup_dir/" &&
cp M300_HOST/payload/{m300_native_probe.py,m300_native_motion.py,m300_pad_mesh.py} "$HOME/klipper/klippy/extras/" &&
sudo systemctl restart klipper.service
```

After Fluidd reconnects, issue `FIRMWARE_RESTART` once to clear the previous
MCU shutdown. Restarting the whole service reloads the changed Python modules.
The update preserves `printer.cfg`, PID, saved mesh profiles and optional
temperature settings. New installations receive these modules automatically.

Software regression tests cover the native contact failure, 100 mm clearance,
Z limits, stuck PC7, invalidated Z, a subsequent home and refusal of recovery
after a controller fault. Physical printer acceptance remains required.

## Separate heating failure

The supplied log first shows unstable PC7 contact with a stable 260°C nozzle.
After the restart, a warm reheat starts near 231°C, initially cools to around
226°C despite a 100% PWM request, and then starts rising. Native heater
verification stops that attempt. This change removes forced shutdown for
recognized contact failures. It does not change PID, `verify_heater`,
temperature limits or MCU guards, and does not establish that the delayed
heater response has been resolved.

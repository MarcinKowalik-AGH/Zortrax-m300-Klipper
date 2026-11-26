# No nozzle contact during homing or bed measurement

Host R16.17, 26 November 2026. Existing MCU firmware 1.0.9 is sufficient.

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

After a complete, successful physical Z home with five contact/release
references, the preceding contact notice is dismissed automatically. The RGB
indicator returns to the current printer state; error history is retained.
An XY-only home or a failed Z attempt cannot dismiss it. A new error received
during homing and all fatal heater/MCU alarms remain active. A missing native
`m300_z_reference` trigger is classified as contact error #042, including
messages containing the cleaning instructions.
The preceding failed mesh retains its `FAILED` result and diagnostic readings;
verified contact recovery releases only its alarm and resource ownership.

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
cp -p "$HOME/klipper/klippy/extras/"{m300_native_probe.py,m300_native_motion.py,m300_pad_mesh.py,m300_errors.py,m300_error_codes.py} "$backup_dir/" &&
cp M300_HOST/payload/{m300_native_probe.py,m300_native_motion.py,m300_pad_mesh.py,m300_errors.py,m300_error_codes.py} "$HOME/klipper/klippy/extras/" &&
sudo systemctl restart klipper.service
```

After Fluidd reconnects, issue `FIRMWARE_RESTART` once to clear the previous
MCU shutdown. Restarting the whole service reloads the changed Python modules.
The update preserves `printer.cfg`, PID, saved mesh profiles and optional
temperature settings. New installations receive these modules automatically.

Software regression tests cover the native contact failure, 100 mm clearance,
Z limits, stuck PC7, invalidated Z, a subsequent home and refusal of recovery
after a controller fault. Physical printer acceptance remains required.

## Warm reheat after a restart

Two operator logs show delayed temperature response when reheating a hot nozzle.
With a 230°C target, the reading initially falls from about 192°C to 189°C
despite a 100% PWM request. It starts recovering near the end of the native
20-second verification window and rises to about 195°C even after the shutdown
cuts power. The preceding cold warmup showed a steady temperature rise.

R16.17 uses the following native configuration for new installations and adds
it during upgrades only when no verification section already exists:

```ini
[verify_heater extruder]
check_gain_time: 40
```

For an existing installation, add this section before the `SAVE_CONFIG` block
in `printer.cfg`, then issue `FIRMWARE_RESTART`. If an include already defines
it, edit that section instead of adding a duplicate. Existing operator choices
are preserved by the installer. Native `heating_gain=2`, `hysteresis=5` and
`max_error=120` remain the defaults; PID, temperature limits and MCU guards
remain active.

Replaying the measured initial observations reproduces the 20-second shutdown;
the 40-second configuration keeps waiting within that observed interval. This
does not establish that the physical nozzle reaches its target. Before printing,
observe a supervised nozzle-only 230°C warmup. If normal heating does not recover,
check the heater, sensor mounting and wiring instead of increasing further limits.

## Tune navigation

`START_PRINT ... MESH=AUTO` loads a saved profile without running a new mesh.
The independent mesh observer owns automatic Tune navigation. R16.17 blocks
that navigation during printing, pausing or an active virtual SD file. Independent
operator mesh measurements retain their normal Tune navigation. Update only
Fluidd, including while Klipper is shut down, with:

```bash
cd "$HOME/m300-orange-pi" &&
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py --update-fluidd --port 4480
```

Reload Fluidd after updating.

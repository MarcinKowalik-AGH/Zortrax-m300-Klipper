# v1.0.0-beta.7 — repair safe upgrades from published beta.4 and beta.5

**Target:** Zortrax M300 Classic / host R16.12. Supersedes
v1.0.0-beta.6, retaining its Cartesian OLED Home/Move animations,
menu cursor restoration, mesh visualization, OLED ACK recovery and native
motion, heater and probe safety policies.

## Why your beta.6 update refused the verified runtime

A reproducible migration oversight affected the host installer: comparing
the immutable `orange-pi` deployment manifests for verified beta.4
(commit `0cc51c9` / source `4cb23fea`) and verified beta.5
(deploy `a72f3a97` / source `9a994b2d`) with the beta.6 package showed
five updated host files that were **missing** from
`SUPPORTED_BASELINES.json`:

| Module | Published prior SHA-256 |
|---|---|
| `m300_activity_graphics.py` | `9e9987006e5bf99826457bb10621fbaf451e063bdebcba6c8ec30149f17a43ac` |
| `m300_menu.py` | `e514682d2701f6cd3a2e13a6b69d971386ab3fe8bdf5442b3764f0261b25e205` |
| `m300_menu_ui.py` | `ddb15cb7fcea9036b3ef0ba2f12ce6e511c38f26d0a2030aa686451a3c2d8187` |
| `m300_oem_graphics.py` | `26b4b59db4728f29810020ee249163b03e2fa66f229acaaaa0d6f2e1df110641` |
| `m300_oled.py` | `452735554fd3b54798a3af6563bfd760f35a2a6045a4e260ed0ae274947c5434` |

Both published beta.4 and beta.5 manifests have these same five hashes.
The first beta.6 module guard thus refused `m300_menu.py` from an otherwise
official previous version. Adding the menu hash alone would expose the next
four omissions, hence all five are fixed together. Existing unrelated
source/config checks, unknown-module rejection and rollback remain active.

A packaged fixture now records the exact verified beta.4, beta.5 and beta.6
deployment manifests. A regression test ensures each previous module SHA is
either already identical to the new payload or explicitly whitelisted.
A separate test verifies that an unknown local `m300_menu.py` still
causes a refusal without writing and now includes its SHA-256 in the error.

## Upgrade an existing M300 Classic on Orange Pi

Ensure the printer has finished starting Klipper, shows **Ready** and is
**idle** (not printing, paused, heating for a procedure, or in Shutdown).
The readiness gate is separate from the module-version problem and is
deliberately unchanged. Run from the Orange Pi terminal:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

After successful installation, hard-refresh Fluidd with
`Cmd+Shift+R` on macOS or `Ctrl+Shift+R` elsewhere. This is a host/
Fluidd update only: **do not reflash the MCU or bootloader**.

If it still refuses `Existing unknown M300 runtime module`, do **not**
delete the installed Python module, patch its hashes manually or use a
force/skip option. Read the actual on-disk file hash, for example:

```bash
sha256sum /home/klipper/m300-test01-0.13.2/klipper/klippy/extras/m300_menu.py
```

If the printed digest does not match the official prior hash above (or the
new package payload), the running file contains other changes and needs a
separate source comparison before it can be safely replaced. Preserve its
contents for a differential review. A failed preflight has written no
files, so no MCU flash or restoring from backups is needed for that refusal.

## Validation boundary

Release publication requires GitHub Actions MCU ARM, 680 host regressions,
nine repository contracts, prior-version migration checks, native Klippy
FILEOUTPUT, tested installers, production Fluidd build and checksums.
Software passing does not guarantee unattended mechanical homing or
contact-probe qualification on the physical machine.

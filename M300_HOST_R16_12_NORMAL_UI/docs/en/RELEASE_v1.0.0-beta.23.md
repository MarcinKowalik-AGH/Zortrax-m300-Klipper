# M300 Classic beta.23 — persistent Fluidd selection and trustworthy acceptance

Supersedes beta.22. Motion, heaters, menu artwork, mesh and MCU firmware are
unchanged: `0.13.14.19-TONED-OLED-UART8`. Do not reflash
`MCU/M300_R14_19_SD.zip` for this update. The illustrated beta.20 handbook
remains an explicitly versioned visual reference.

Both installers prefer **Fluidd port 4480**, support explicit overrides,
revalidate a saved endpoint, and only fall back to a single unambiguous nginx
Fluidd installation. The successful port/root receipt lives beside the active
printer.cfg as `.m300-installer.json`, outside the integrity-protected Git
package. Existing KIAUH port 80 or legacy 4080 deployments are not silently
moved. Ambiguity or a changed saved endpoint requires operator selection.

The current Polish PRINT_CONTROL manual now describes four startup extrusion
segments **2Y + 2X**, native mesh activation after homing and actual geometry
bounds. The old single-line 40 mm description is explicitly historical.

A trusted-default-branch `workflow_run` policy can retry recognized transient
network/infrastructure failures, at most twice (three total attempts), with
30/60-second backoff. It inspects the failed step logs, rechecks the exact SHA
and attempt, rejects forks/superseded commits, never executes artifacts or PR
code, and refuses test/compiler/checksum/permission/unknown failures. Normal
successful-build release gates remain unchanged. Audit decisions are retained.

A single JSON-backed acceptance register records function, version, test,
result, issue and evidence. CI is never promoted into physical acceptance.
Known UI confirmations are preserved; unconfirmed physical tests stay pending.

## Upgrade

Only while the printer is idle and Ready, as the Klipper account:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Refresh Fluidd. After a successful update the port argument may be omitted;
the saved endpoint is checked again against nginx. No firmware flashing, new
mesh, motion/heating commands or manual checksum bypass is necessary.

[Installer and retry details (PL)](../pl/INSTALLATION_AND_CI.md),
[print procedure (PL)](../pl/PRINT_CONTROL.md),
[acceptance register (PL)](../pl/ACCEPTANCE_REGISTER.md).

Publication requires the matching full build and deployment, all 741 host
regressions, installer migration tests, new port/retry/ledger tests, ARM,
native Klippy, Fluidd and package checksums. Mocked network failures validate
the decision policy; they do not simulate physical printer performance or
prove a real future GitHub service outage has already been recovered.

# M300 beta.24 — qualified first-print Z profile and 2 mm contact clearance

The user report from 11 November 2026 records successful heating, homing and
entry into printing after a Z configuration correction. It does not confirm
completion of the Benchy, first-layer quality or complete hardware acceptance.
[Original report](../evidence/M300_FIRST_PRINT_USER_REPORT_2026-11-11.md) and
[detailed Polish instructions](../pl/RELEASE_v1.0.0-beta.24.md) preserve that scope.

At X3/Y10, mesh correction was -0.369086 mm: purge Z0.28 became -0.089086 mm,
below the old software minimum 0. The qualified machine uses position_min=-0.5,
M07 safe_z=5, approach_distance=6.5 and probe_search_margin=1. The relationship
6.5 >= 5 + 1 - (-0.5) remains enforced. Do not disable mesh, shift contact zero,
move the purge lines or use FORCE_MOVE as a workaround.

The later user request changes contact clearance to 2 mm. Previously the
initial/second-pass retreat silently imposed max(5, configured value). That
floor is removed; the option now has an explicit 2 mm minimum and keeps its
5 mm default. PC7 must still be open before XY and the second contact pass;
stuck contact, invalid reference and insufficient axis room still stop motion.
The independent M07 safe_z remains 5. Other Z probe refinements are unchanged.

## Existing installation, only while idle and Ready

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480 --qualified-first-print-z
```

The explicit flag selects the mechanically qualified -0.5/6.5/2 configuration.
It updates existing sections and preserves includes, saved mesh, PID, XY limits,
UART and purge geometry. Unknown custom values, duplicate sections or saved
conflicts are refused; installation uses the existing backup/rollback mechanism.
Ordinary updates without the flag do not lower geometry limits. Global first
installation templates retain Z minimum 0 and clearance 5. Previously selected
settings remain in place on later ordinary upgrades.

Inspect ZORTRAX_MOTION_STATUS after restart: z_contact_clearance_mm and
z_initial_clearance_mm should report 2, with motion revision
0.13.16.24-QUALIFIED-Z-CLEARANCE. No MCU flash is required; the firmware remains
0.13.14.19-TONED-OLED-UART8. Do not reflash MCU/M300_R14_19_SD.zip for this update.
The pre-existing M300305/105 temperature-policy changes are preserved, not
introduced or claimed qualified by this note. Temperature waiting behavior,
mesh, four startup lines, heating protections and OLED graphics are unchanged.
The 65-screen handbook remains a versioned beta.20 visual reference.

Programmatic validation covers both 5 and 2 mm retreats, actual native coarse
homing in a modeled harness, stuck PC7, range errors, M07 negative-Z geometry,
installer idempotence/refusal/rollback and existing host regressions. Real
first-layer and long-print acceptance are still pending and recorded as such.

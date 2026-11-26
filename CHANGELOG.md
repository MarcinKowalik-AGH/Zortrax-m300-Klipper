# Changelog — Zortrax M300 Classic

## 1.0.4 — 26 November 2026

Host 1.0.4 / R16.19, MCU 1.0.9. Consolidated download with optional USB camera,
independent Host/MCU temperature graphs, internal STM32 diagnostics, contact
recovery, resolved contact lighting, delayed warm-reheat handling and OLED
menu corrections. Includes complete Git/ZIP installation on Python 3.12/3.13,
current PL/EN instructions, the new operator screenshot and the menu audit.

[English release notes](docs/en/RELEASE_v1.0.4.md) · [Opis po polsku](docs/pl/RELEASE_v1.0.4.md) · [Download](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/v1.0.4)

## 1.0.3 — 24 November 2026

Immutable earlier release snapshot: planned-restart supervision and mesh
cancellation. Later fixes were first distributed through `orange-pi` and are
collected in 1.0.4. Historical release notes retain their original scope.

[English notes](docs/en/RELEASE_v1.0.3.md) · [Polski](docs/pl/RELEASE_v1.0.3.md)

Software test results and physical acceptance are tracked separately in the
[hardware register](docs/pl/ACCEPTANCE_REGISTER.md). Earlier accepted results
are retained; a new release does not turn pending hardware tests into PASS.

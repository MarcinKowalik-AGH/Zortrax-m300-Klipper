# M300 Classic 1.0.3 — mesh, Cancel i restart

24.11.2026. Host **1.0.3**, MCU **1.0.8**.

- Heartbeat pozostaje aktywny podczas opróżniania kolejki przed restartem.
  Nowe żądania ruchu i grzania są blokowane. Restart ma limit 120 sekund;
  odłączenie, shutdown i nieprawidłowy stan MCU zatrzymują nadzór.
- `SAVE_CONFIG` i `RESTART` resetują również MCU, aby nowy host ustanowił
  własną sesję ARM. Nie ma automatycznego kasowania błędów zabezpieczeń.
- Cancel z Fluidd unieważnia aktywny mesh, także gdy pomiar trzyma mutex G-code.
  Wyłącza cele grzałek. Parkowanie czeka na zakończenie obsługi pomiaru i ruchów;
  kolejny plik można rozpocząć po zakończeniu anulowania.
- Instalator rozpoznaje poprzedni opublikowany parser i zachowuje możliwość rollback.

999 testów hosta; scenariusze są symulowane i nie stanowią odbioru drukarki.
Poprawki nie dowodzą usunięcia osobnego błędu grzania z logu: cel 230°C,
raportowane PWM 100%, spadek odczytu około 218–215°C. Nadzór `verify_heater`
i zabezpieczenia MCU nie zostały poluzowane. Sprawdzenie grzania na maszynie
pozostaje wymagane przed uznaniem tej awarii za usuniętą.

Aktualizacja przy bezczynnej drukarce w stanie Ready, cele grzałek wyłączone:

```bash
cd "$HOME/m300-orange-pi" &&
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

Sprawdź `ZORTRAX_INFO REFRESH=0`: host 1.0.3, MCU 1.0.8. MCU 1.0.8 nie
wymaga ponownego flashowania. Próba sprzętowa: mesh → SAVE_CONFIG → Ready,
a następnie Cancel → zakończenie parkowania → start nowego pliku. Zachowaj log.

Osobna naprawa Fluidd: `python3 install-orange-pi.py --update-fluidd --port 4480`.

Pełny pakiet zachowuje `M300_SD.zip` z MCU 1.0.8 dla drukarek wymagających aktualizacji firmware. Ilustracje OLED w podręczniku zachowują oznaczoną historyczną bazę beta.20.

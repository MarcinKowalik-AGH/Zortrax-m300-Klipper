<!-- Marcin Kowalik <mkowalik@agh.edu.pl> | RELEASE_v1.0.0-rc.31.md - Opisuje tryb auto i migrację nastaw wyładunku oraz załadunku filamentu. -->
# M300 Classic RC31 — automatyczne i własne nastawy filamentu

W istniejącej sekcji `[m300_filament]` każde z czterech pól przyjmuje `auto` lub liczbę. Nastawy działają wspólnie na OLED, we Fluidd i w OrcaSlicerze, również podczas wymiany materiału poleceniem `M600`.

```ini
unload_temperature: auto
unload_speed: auto
load_temperature: auto
load_speed: auto
```

Wartość `auto` wybiera 240°C dla każdej z dwóch temperatur i dotychczasowe 2 mm/s dla każdej z dwóch prędkości. Przy wydruku w 210°C dysza wykonuje wyładunek i załadunek przy 240°C. Dopiero po zakończeniu wymiany wraca nastawa 210°C. Potwierdzenie włożenia filamentu i wznowienie wydruku pozostają oddzielnymi czynnościami operatora.

Aby sprawdzić wpływ jednej zmiany, możesz np. wpisać `unload_speed: 3` i pozostawić `auto` w pozostałych trzech polach. Prędkość dotyczy przesuwu filamentu w mm/s. Komendy materiałowe z opcjonalnym `TEMP` przyjmują także `TEMP=auto` dla pojedynczej operacji. W `ZORTRAX_CHANGE` parametr ten dotyczy ładowania.

## Aktualizacja Orange Pi

Po zakończeniu druku, w stanie Ready z wyłączonymi grzałkami, wykonaj w katalogu gałęzi `orange-pi`:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

Instalator przepisuje standardowy zestaw RC30 na cztery wpisy `auto`. W dostrojonej konfiguracji zachowuje własne liczby, a dawne `load_temperature: 0` zamienia na `auto`. Po własnej edycji konfiguracji wykonaj `RESTART` w spoczynku. Polecenie `ZORTRAX_FILAMENT_STATUS` pokazuje wpisane opcje w polu `configured_material` oraz odpowiadające im wartości liczbowe.

MCU 1.0.8 obsługuje RC31. Oddzielne archiwum firmware to `M300_SD.zip`. Fluidd działa na porcie 4480, a jego osobny instalator przyjmuje `--update-fluidd --port 4480`. Część ilustracji instrukcji pochodzi z beta.20.

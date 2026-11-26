# Brak styku dyszy podczas bazowania lub pomiaru stołu

Host R16.16, 26.11.2026. Firmware MCU 1.0.9 pozostaje wystarczający.

Rozpoznany brak lub niestabilność styku PC7 przerywa pomiar i wyłącza cele
grzałek. Gdy natywne położenie Z jest znane, host opuszcza stół o **100 mm**,
z prędkością nie większą niż 5 mm/s. Jeśli do dolnego końca zakresu Z zostało
mniej miejsca, dojeżdża tylko do tego limitu. Nie wykonuje ruchu XY ani
ponownego podejścia do dyszy. Stół pozostaje opuszczony do kolejnego bazowania.

Następnie unieważnia odniesienie Z i wyświetla komunikat
`No contact - please clean nozzle and pad contacts, then repeat homing.`
Nie zapisuje nieudanego meshu. Po wyczyszczeniu dyszy i pól kontaktowych
ponów bazowanie, a następnie pomiar; ten błąd styku nie wymaga
`FIRMWARE_RESTART`. Potwierdź komunikat błędu, jeśli zasłania panel procedur.

Po pełnym, udanym bazowaniu Z z pięcioma odniesieniami zwarcie/rozwarcie
wcześniejszy komunikat błędu styku wygasa automatycznie. LED wraca do koloru
bieżącego stanu drukarki zamiast nadal cyklicznie zmieniać RGB. Historia błędu
pozostaje dostępna. Samo bazowanie X/Y ani nieudana próba Z nie wygaszają
alarmu. Nowy błąd zgłoszony w czasie bazowania oraz alarmy grzania i MCU
zachowują swój stan. Brak wyzwolenia `m300_z_reference` jest oznaczany kodem
kontaktu #042, również gdy komunikat zawiera instrukcję czyszczenia.
Poprzedni nieudany mesh zachowuje wynik `FAILED` i odczyty diagnostyczne;
potwierdzony powrót styku zwalnia jedynie jego alarm i zajętość zasobów.

Jeżeli pierwsze bazowanie nie ustaliło Z, host nie wykonuje dodatkowego
ruchu w nieznanym układzie. Informuje o braku odniesienia. Stale zwarty PC7
po opuszczeniu stołu wymaga również sprawdzenia połączeń styku.
Awaria MCU, transmisji lub ruchu nadal może wymagać shutdown i restartu;
nie uruchamia się wówczas procedury opuszczania stołu.

## Aktualizacja istniejącego hosta

Wykonaj przy bezczynnej drukarce, z wyłączonymi celami grzałek:

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

Po ponownym połączeniu Fluidd wykonaj jednorazowo `FIRMWARE_RESTART`, aby
usunąć poprzedni shutdown MCU. Pełny restart usługi jest potrzebny do
wczytania zmienionych modułów Pythona. Instalacja zachowuje `printer.cfg`,
PID, zapisane profile meshu i ustawienia opcjonalnych temperatur.

Nowa instalacja otrzymuje te moduły automatycznie. Sprawdzenie programowe
obejmuje utratę styku w natywnym pomiarze, prześwit 100 mm, limity Z,
zwarcie PC7, unieważnienie Z, ponowne bazowanie oraz odmowę ruchu po awarii.
Potwierdzenie zachowania na drukarce pozostaje wymagane.

## Osobny komunikat grzania

W dostarczonym logu najpierw występuje niestabilny PC7 przy utrzymywanej
temperaturze 260°C. Po restarcie dysza dogrzewa się z około 231°C, początkowo
stygnie do około 226°C mimo żądania PWM 100%, a następnie zaczyna rosnąć.
Natywny nadzór grzania zatrzymuje tę próbę. Ta poprawka usuwa wymuszony
shutdown dla rozpoznanego błędu styku; nie zmienia PID, `verify_heater`,
limitów temperatur ani zabezpieczeń MCU i nie stanowi potwierdzenia
usunięcia przyczyny opóźnionej reakcji grzałki.

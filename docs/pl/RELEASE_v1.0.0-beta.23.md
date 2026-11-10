# M300 Classic beta.23 — instalator 4480, aktualny START, retry CI i odbiory

Zastępuje beta.22. **Nie zmienia ruchu, temperatur, ikon, menu, mesh ani firmware
MCU.** Pozostaje `0.13.14.19-TONED-OLED-UART8`; nie trzeba wgrywać ponownie
`MCU/M300_R14_19_SD.zip`. Historyczna ilustrowana instrukcja 65 ekranów beta.20
pozostaje oznaczonym punktem odniesienia; te poprawki jej grafik nie zmieniają.

## Cztery domknięte zadania

Instalatory aktualizacji i pierwszego uruchomienia preferują **4480**,
zapamiętują poprawnie rozpoznany port/katalog poza repozytorium i weryfikują
zapis przy kolejnej aktualizacji. Jawne parametry mają pierwszeństwo. Inne
jednoznaczne instalacje pozostają wspierane; nginx nie jest przełączany na
inny port bez wiedzy operatora.

Instrukcja PRINT_CONTROL opisuje obecny start **2Y + 2X**, rzeczywiste domyślne
parametry, ograniczenie ścieżki do M300 oraz ładowanie siatki po bazowaniu.
Opis jednej linii 40 mm przeniesiono do wyraźnie oznaczonego archiwum.

Ograniczony automat GitHub Actions ponawia wyłącznie rozpoznane przejściowe
błędy sieciowe/infrastruktury. Maksymalnie dwa ponowienia. Błędy kodu, testów,
sum i nieznane awarie nadal blokują publikację. Klasyfikator nie wykonuje kodu
PR ani artefaktów, nie pomija testów i nie aktualizuje drukarki.

Wspólny rejestr odbiorów przechowuje funkcję, wersję, próbę, wynik, problem oraz
źródło potwierdzenia. Jawnie rozdziela wyniki CI, zaakceptowane UI, częściowe
obserwacje i testy oczekujące. Nie dopisano nieprzeprowadzonych testów sprzętu.

## Aktualizacja

Przy **Ready**, bez aktywnego/wstrzymanego wydruku ani procedury, jako klipper:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Odśwież Fluidd przez Cmd+Shift+R. Po udanej instalacji port i katalog są zapisane
w `.m300-installer.json` obok aktywnego printer.cfg. Kolejna aktualizacja może
pominąć parametr portu. Nie zmieniaj ręcznie plików objętych SHA256SUMS.

[Instalator i CI](INSTALLATION_AND_CI.md) · [Aktualny START](PRINT_CONTROL.md) ·
[Rejestr odbiorów](ACCEPTANCE_REGISTER.md).

Publikacja wymaga pełnego CI: istniejących 741 testów hosta, testów migracji,
nowych testów wyboru portu i retry, spójności rejestru, kompilacji ARM,
natywnego Klippy, Fluidd i integralności pakietu. Testy z atrapami API nie są
celowo wywołaną awarią GitHuba, a udany build nie potwierdza fizycznego druku.

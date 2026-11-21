# Zortrax M300 Classic 1.0.0 — 21.11.2026

Finalne wydanie źródeł: **host 1.0.0 + MCU 1.0.8**, z projektowym Fluidd na
porcie **4480**. Wersja zastępuje RC34. [Audyt końcowy](AUDYT_FINAL_2026-11-21.md)
opisuje sprawdzone procedury, poprawki i otwarte próby sprzętowe.

Odrzucone żądanie zmiany filamentu mogło wcześniej oznaczyć poprawną pauzę jako
wymagającą ukończenia wymiany. Przez makro operatora błędna temperatura mogła
również uruchomić parkowanie, a potem zakończyć sterownik druku błędem. Teraz
wspólna walidacja sprawdza plan transportu i temperatury przed żądaniem pauzy
lub parkowania. Właściciel filamentu oznacza wymianę jako rozpoczętą dopiero po
przejściu warunków wstępnych. Odrzucenie przed rozpoczęciem wymiany, również
po zmianie gotowości w czasie parkowania, zachowuje pauzę i jej dotychczasowe
uprawnienia do wznowienia. Awaria rozpoczętej procedury nadal wyłącza grzanie
i uruchamia istniejącą obsługę błędu.

Uporządkowano walidację żądań, spis procedur, bieżące odnośniki instalacji oraz
oznaczenia historycznych audytów. Publikator obsługuje finalny tag i sprawdza
niezmienność istniejących wydań. Pozostaje 36 makr operatora `M300_` i zgodność
ze starszymi nazwami. Algorytmy kontaktu, MCU, limity grzania, chłodzenie, UART
i transport OLED zachowują wcześniejsze działanie. Testy programu nie zamykają
rejestru odbiorów sprzętowych.
Instalator rozpoznaje dokładne moduły RC34 podlegające wymianie i nadal chroni
własne zmiany operatora. Nowa regresja i migracja dostarczonego zrzutu
sprawdzają aktualizację, idempotencję oraz dokładne cofnięcie zmian.

## Aktualizacja

Zakończ aktywną operację, poczekaj na Ready i wyłącz cele obu grzałek.
W istniejącym klonie gałęzi `orange-pi` wykonaj:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

Osobna aktualizacja lub naprawa projektowego Fluidd:

```bash
python3 install-orange-pi.py --update-fluidd --port 4480
```

Po aktualizacji odczytaj `ZORTRAX_INFO REFRESH=0`: host **1.0.0**, MCU **1.0.8**.
Zainstalowane MCU 1.0.8 nie wymaga ponownego wgrywania dla tej poprawki hosta.
Jeśli jest potrzebne, rozpakuj `M300_SD.zip` z pełnego wydania, sprawdź sumy
i wgraj `M300APP.M3B` przez istniejący zgodny bootloader.

[Pierwsza instalacja](FIRST_INSTALL.md) · [Aktualizacja i cofanie zmian](INSTALL.md) ·
[Rejestr prób](ACCEPTANCE_REGISTER.md). Ilustrowany katalog OLED zachowuje
oznaczoną historyczną bazę beta.20.

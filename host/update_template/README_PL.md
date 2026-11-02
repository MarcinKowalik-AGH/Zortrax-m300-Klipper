# M300 host R15.6 — natywne menu i ekran usypiania OEM

[English](README.md) · [Instalacja](docs/pl/INSTALL.md) · [Zachowanie](docs/pl/BEHAVIOUR.md) · [Stan](docs/pl/STATUS.md)

Aktualizacja działającej **M300 Classic: natywny host R15.5 + MCU R14.4**.
Przywraca odwołania menu do natywnych poleceń, zgubione w R15.5, i dodaje
obsługę bezczynności ekranu **0.2.0-M300-OEM-SLEEP**.

| Po 5 minutach bez obsługi operatora | OLED |
|---|---|
| Druk, pauza, procedura, oczekujący ruch lub zadana temperatura | Przygaszenie; wskazania są aktualizowane |
| Bezczynność | Oryginalny księżyc i **Entering sleep mode**, następnie wygaszenie po 10 sekundach potwierdzonego wyświetlania |
| Pokrętło lub polecenie G-code z interfejsu | Wybudzenie; pierwszy niewidoczny gest nie wybiera opcji |

Napis i piksele księżyca sprawdzono w oryginalnym M300 1.3.1. Przeniesiono
prezentację. Nie przeniesiono wyłączania urządzeń ani grzania stołu przy
wybudzaniu, które występują w fizycznej procedurze OEM.

Instalator aktualizuje menu i listę akcji M11, dodaje cztery pliki wyświetlacza
oraz, gdy potrzeba, konfigurację i include. Zachowuje istniejące ustawienia
wyświetlacza i obsługuje aktualizację wcześniejszego dodatku 0.1. Nieznane
lokalne modyfikacje powodują odmowę. Powstaje kopia do dokładnego cofnięcia.

**MCU R14.4 pozostaje w drukarce. Ta paczka nie zawiera wsadu do flashowania.**
Po aktualizacji nie instaluj ponownie pełnej starszej paczki R15.5, ponieważ
zastąpiłaby naprawione menu.

Sprawdzenie paczki: `python3 VERIFY.py`; testy:
`python3 -m unittest discover -s tests -v` — **71 przypadków**.
Dodatkowe wyniki hosta, kompilacji ARM i rzeczywistych procesów Klippy
FILEOUTPUT są w REPORTS pełnego artefaktu Actions. Nie wykonywano nowych prób
na drukarce. Otwarte kwestie geometrii Z, temperatury i wydajności opisuje audyt.
